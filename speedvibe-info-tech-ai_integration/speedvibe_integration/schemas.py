from pydantic import BaseModel, Field, HttpUrl


class SpeedvibeChatRequest(BaseModel):
    message: str = Field(..., description="User message")


class SpeedvibeChatResponse(BaseModel):
    response: str = Field(..., description="Assistant reply")


class SpeedvibeScrapeRequest(BaseModel):
    website_url: HttpUrl | None = Field(
        default=None,
        description="Override base URL; defaults to SPEEDVIBE_BASE_URL from env",
    )
    max_pages: int = Field(default=50, ge=1, le=200)


class SpeedvibeScrapeResponse(BaseModel):
    message: str
    status: str


class SpeedvibeKnowledgeStats(BaseModel):
    total_documents: int
    collection_name: str
    database_type: str = "ChromaDB"


class SpeedvibeSearchResult(BaseModel):
    content: str
    source_url: str
    page_title: str | None
    similarity: float


class SpeedvibeSearchResponse(BaseModel):
    query: str
    results: list[SpeedvibeSearchResult]
