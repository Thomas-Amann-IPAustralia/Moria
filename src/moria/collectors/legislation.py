"""The Federal Register of Legislation (OData API): every version registered in the window, and every new title.

All Commonwealth legislation is collected, not only IP law: changes anywhere can travel to the IP system (design §2).
The API's datetimes carry no zone, and its timezone is unconfirmed. Windows are contiguous in the API's own clock,
so nothing falls between them.
"""

from __future__ import annotations

from ..config import Strict
from ..records import RawRecord, make_envelope
from .base import CollectContext

PARSER_VERSION = "legislation-v1"
VERSION_FIELDS = "titleId,name,status,registeredAt,start,end,compilationNumber,isLatest,isCurrent,registerId"
TITLE_FIELDS = (
    "id,name,collection,subCollection,makingDate,status,isPrincipal,isInForce,asMadeRegisteredAt,seriesType,year,number"
)


class LegislationParams(Strict):
    base_url: str = "https://api.prod.legislation.gov.au/v1"
    page_size: int = 100


def _odata_time(moment) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


class LegislationCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = LegislationParams.model_validate(card.params)

    def _pages(self, ctx: CollectContext, entity: str, field: str, select: str) -> list[dict]:
        rows: list[dict] = []
        start, end = _odata_time(ctx.window.start), _odata_time(ctx.window.end)
        skip = 0
        while True:
            params = {
                "$filter": f"{field} ge {start} and {field} lt {end}",
                "$select": select,
                "$orderby": f"{field},{select.split(',')[0]}",
                "$top": str(self.params.page_size),
                "$skip": str(skip),
            }
            page = ctx.client.get(f"{self.params.base_url}/{entity}", params=params).json().get("value", [])
            rows.extend(page)
            if len(page) < self.params.page_size or (ctx.limit and len(rows) >= ctx.limit):
                return rows[: ctx.limit] if ctx.limit else rows
            skip += self.params.page_size

    def _record(
        self, row: dict, entity: str, record_id: str, observable_at: str | None, event_at: str | None
    ) -> RawRecord:
        payload = {"entity": entity, **row}
        return RawRecord(
            envelope=make_envelope(
                provider="Federal Register of Legislation",
                source_collection=f"frl_{entity.lower()}",
                provider_record_id=record_id,
                kind="document",
                family=self.card.family,
                rings=self.card.rings,
                domains=self.card.domains,
                payload=payload,
                request={"entity": entity, "id": record_id},
                retrieval_method=f"odata:frl:{entity}",
                tool_identity=f"moria:{PARSER_VERSION}",
                licence=self.card.licence,
                parser_version=PARSER_VERSION,
                event_at=event_at,
                observable_at=observable_at,
            ),
            payload=payload,
        )

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        records = []
        for v in self._pages(ctx, "Versions", "registeredAt", VERSION_FIELDS):
            rid = f"{v.get('titleId')}|{v.get('compilationNumber')}|{v.get('registeredAt')}"
            records.append(self._record(v, "Versions", rid, v.get("registeredAt"), v.get("start")))
        for t in self._pages(ctx, "Titles", "asMadeRegisteredAt", TITLE_FIELDS):
            records.append(
                self._record(t, "Titles", str(t.get("id")), t.get("asMadeRegisteredAt"), t.get("makingDate"))
            )
        return records
