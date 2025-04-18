"""
Handlers for debug endpoints.
"""

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config import MAX_LOG_ENTRIES
from utils import request_logs

async def get_logs(limit: int = 10, request_id: str = None):
    """
    Endpoint to view recent request/response logs for debugging
    """
    if limit > MAX_LOG_ENTRIES:
        limit = MAX_LOG_ENTRIES
        
    if request_id:
        # Filter logs by request_id
        filtered_logs = [log for log in request_logs if log["request_id"] == request_id]
        return JSONResponse(content={"logs": filtered_logs})
    else:
        # Return most recent logs up to limit
        return JSONResponse(content={"logs": list(request_logs)[:limit]})

async def get_request_detail(request_id: str):
    """
    Get detailed information about a specific request by ID
    """
    for log in request_logs:
        if log["request_id"] == request_id:
            return JSONResponse(content=log)
    
    raise HTTPException(status_code=404, detail="Request ID not found in logs")
