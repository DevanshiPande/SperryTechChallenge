"""Gemini client: JSON-schema calls, text calls, tool-calling chat. Caching, timeouts, one retry, fake mode.

Gemini only reads text and writes words. Every caller validates what comes back."""
import base64
import hashlib
import json
import logging
import os
import time

log = logging.getLogger("gridlock.gemini")


class GeminiUnavailable(Exception):
    pass


# ---------- config ----------
def api_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def model_name():
    return os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


def timeout_s():
    return float(os.environ.get("GEMINI_TIMEOUT_S", "20"))


def fake_mode():
    return os.environ.get("FAKE_GEMINI", "0") == "1"


def available():
    return fake_mode() or bool(api_key())


# ---------- fake mode ----------
# Tests push scripted responses here. Each item is returned once, in order, by the next call in fake mode.
# For chat_with_tools an item is {"text": ...} or {"calls": [{"name", "args"}]}.
FAKE_SCRIPT = []


def fake_push(*items):
    FAKE_SCRIPT.extend(items)


def fake_reset():
    FAKE_SCRIPT.clear()


def _fake(default):
    if FAKE_SCRIPT:
        item = FAKE_SCRIPT.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    return default() if callable(default) else default


# ---------- cache ----------
class MemoryCache:
    def __init__(self):
        self.d = {}

    def get(self, key):
        return self.d.get(key)

    def set(self, key, value):
        self.d[key] = value


_cache = MemoryCache()


def set_cache(cache):
    """cache: object with get(key) and set(key, value). Mongo-backed in normal mode."""
    global _cache
    _cache = cache


def cache_key(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


# ---------- client ----------
_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        from google.genai import types
        _client = genai.Client(api_key=api_key(), http_options=types.HttpOptions(timeout=int(timeout_s() * 1000)))
    return _client


def reset_client():
    global _client
    _client = None


def _NO_AFC():
    from google.genai import types
    return types.AutomaticFunctionCallingConfig(disable=True)


def _retryable(e):
    s = str(e).lower()
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    return (isinstance(code, int) and code >= 500) or "timeout" in s or "timed out" in s or "deadline" in s \
        or "unavailable" in s or "503" in s or "500" in s


def _call(fn, what):
    """Run fn with one retry on timeout/5xx. Raises GeminiUnavailable."""
    if not api_key():
        raise GeminiUnavailable("GEMINI_API_KEY is not set")
    last = None
    for attempt in range(2):
        t0 = time.time()
        try:
            out = fn()
            log.info("gemini %s ok model=%s latency_ms=%d attempt=%d", what, model_name(), (time.time() - t0) * 1000, attempt + 1)
            return out
        except GeminiUnavailable:
            raise
        except Exception as e:  # SDK raises several error types
            last = e
            log.warning("gemini %s failed attempt=%d latency_ms=%d error=%s", what, attempt + 1, (time.time() - t0) * 1000,
                        type(e).__name__)
            if not _retryable(e):
                break
    raise GeminiUnavailable(str(last))


def generate_json(prompt, schema, temperature=0.2, fake=None, use_cache=True, system=None):
    """JSON-mode call with a response schema. Returns a dict."""
    if fake_mode():
        return _fake(fake if fake is not None else {})
    key = cache_key(model_name(), system, prompt, schema)
    if use_cache:
        hit = _cache.get(key)
        if hit is not None:
            log.info("gemini json cache_hit")
            return hit

    def run():
        from google.genai import types
        resp = client().models.generate_content(
            model=model_name(), contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature, response_mime_type="application/json",
                                               response_json_schema=schema, system_instruction=system,
                                               automatic_function_calling=_NO_AFC()))
        text = resp.text or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise GeminiUnavailable(f"Gemini returned invalid JSON: {e}")

    out = _call(run, "json")
    if not isinstance(out, dict):
        raise GeminiUnavailable("Gemini returned JSON that is not an object")
    if use_cache:
        _cache.set(key, out)
    return out


def generate_text(prompt, temperature=0.3, fake=None, use_cache=True, system=None):
    if fake_mode():
        return _fake(fake if fake is not None else "")
    key = cache_key(model_name(), system, prompt, "text")
    if use_cache:
        hit = _cache.get(key)
        if hit is not None:
            log.info("gemini text cache_hit")
            return hit

    def run():
        from google.genai import types
        resp = client().models.generate_content(
            model=model_name(), contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature, system_instruction=system,
                                               automatic_function_calling=_NO_AFC()))
        return (resp.text or "").strip()

    out = _call(run, "text")
    if not out:
        raise GeminiUnavailable("Gemini returned an empty response")
    if use_cache:
        _cache.set(key, out)
    return out


def chat_with_tools(system, messages, tools, temperature=0.2, fake=None):
    """One model turn with function calling (no automatic execution).

    messages: [{"role": "user", "text"}, {"role": "model", "text"?, "calls"?: [{name, args}]},
               {"role": "tool", "results": [{name, response}]}]
    tools: [{"name", "description", "parameters"(JSON schema)}]
    Returns {"text": str|None, "calls": [{"name", "args"}]}."""
    if fake_mode():
        return _fake(fake if fake is not None else {"text": "OK.", "calls": []})

    def run():
        from google.genai import types
        contents = []
        for m in messages:
            if m["role"] == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m["text"])]))
            elif m["role"] == "model":
                parts = []
                if m.get("text"):
                    parts.append(types.Part.from_text(text=m["text"]))
                for c in m.get("calls") or []:
                    # Gemini 3 requires the thought signature of each function call to be sent back.
                    sig = base64.b64decode(c["sig"]) if c.get("sig") else None
                    parts.append(types.Part(function_call=types.FunctionCall(name=c["name"], args=c.get("args") or {}),
                                            thought_signature=sig))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif m["role"] == "tool":
                parts = [types.Part.from_function_response(name=r["name"], response={"result": r["response"]})
                         for r in m.get("results") or []]
                if parts:
                    contents.append(types.Content(role="user", parts=parts))
        decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                           parameters_json_schema=t["parameters"]) for t in tools]
        cfg = types.GenerateContentConfig(
            temperature=temperature, system_instruction=system,
            tools=[types.Tool(function_declarations=decls)] if decls else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        resp = client().models.generate_content(model=model_name(), contents=contents, config=cfg)
        calls = []
        cand = (resp.candidates or [None])[0]
        for part in ((cand.content.parts if cand and cand.content else None) or []):
            if part.function_call:
                call = {"name": part.function_call.name, "args": dict(part.function_call.args or {})}
                if part.thought_signature:
                    call["sig"] = base64.b64encode(part.thought_signature).decode()
                calls.append(call)
        text = None
        if not calls:
            try:
                text = (resp.text or "").strip() or None
            except Exception:
                text = None
        return {"text": text, "calls": calls}

    return _call(run, "chat")
