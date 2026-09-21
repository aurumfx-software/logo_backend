from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total_items: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1


class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[T] = None
    errors: Optional[List[Any]] = None


class StandardListResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Operation completed successfully"
    data: List[T] = []
    meta: Optional[PaginationMeta] = None
    errors: Optional[List[Any]] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str = "An error occurred"
    data: Optional[Any] = None
    errors: Optional[List[Any]] = None


def success_response(
    data: Any = None,
    message: str = "Operation completed successfully",
) -> StandardResponse:
    return StandardResponse(success=True, message=message, data=data, errors=None)


def list_response(
    data: List[Any],
    total_items: int,
    page: int = 1,
    page_size: int = 50,
    message: str = "Operation completed successfully",
) -> StandardListResponse:
    total_pages = (total_items + page_size - 1) // page_size if page_size > 0 else 1
    return StandardListResponse(
        success=True,
        message=message,
        data=data,
        meta=PaginationMeta(
            total_items=total_items,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        errors=None,
    )


def error_response(
    message: str = "An error occurred",
    errors: Optional[List[Any]] = None,
    data: Optional[Any] = None,
) -> ErrorResponse:
    return ErrorResponse(
        success=False,
        message=message,
        data=data,
        errors=errors or [],
    )
