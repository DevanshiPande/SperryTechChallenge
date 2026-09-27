"""Request dependencies: caller identity from headers, JSON bodies.

Declared as Header/Body parameters so the interactive docs at /docs show input boxes for them."""
from typing import Optional

from fastapi import Body, Header

from services import identity


def ident(x_company_id: Optional[str] = Header(None, description="Act as a demo company: CMP_A, CMP_B or CMP_C"),
          x_worker_id: Optional[str] = Header(None, description="Act as the demo worker: WRK_1")):
    return identity.resolve(x_company_id, x_worker_id)


def json_body(body: dict = Body(default_factory=dict)):
    return body or {}
