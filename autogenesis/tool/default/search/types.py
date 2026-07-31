from typing import List, Any, Optional
from pydantic import BaseModel, Field

class SearchItem(BaseModel):
    """Represents a single search result item"""

    title: str = Field(description="The title of the search result")
    url: str = Field(description="The URL of the search result")
    date: Optional[str] = Field(default=None, description="The date of the search result")
    position: Optional[int] = Field(default=None, description="The position of the search result in the list")
    source: Optional[str] = Field(default=None, description="The source of the search result")
    description: Optional[str] = Field(default=None, description="A description or snippet of the search result")
    content: Optional[str] = Field(default=None, description="Full scraped content of the search result in markdown")

    def __str__(self) -> str:
        """String representation of a search result item."""
        return f"{self.title} - {self.url} - {self.description or 'No description available'}"
    
class SearchToolArgs(BaseModel):
    """Arguments for the search tool."""
    query: str = Field(description="The query to search for")
    num_results: int = Field(default=5, description="The number of search results to return, default is 5")
    country: Optional[str] = Field(default="us", description="The country to search in, default is us")
    lang: Optional[str] = Field(default="en", description="The language to search in, default is en")
    filter_year: Optional[int] = Field(default=None, description="The year to filter results by, default is None")