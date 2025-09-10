"""
Database Query Executor for safe SQL execution with result formatting.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.database.async_manager import async_db_manager
from src.utils.query_safety import QuerySafetyValidator

logger = logging.getLogger(__name__)


class DatabaseQueryExecutor:
    """Execute SQL queries safely with result formatting and pagination."""
    
    def __init__(self):
        self.safety_validator = QuerySafetyValidator()
        self.max_results = 1000  # Maximum results to return
        self.default_limit = 100  # Default LIMIT if not specified
    
    async def execute_query(self, sql: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute SQL query with safety checks and result formatting.
        
        Args:
            sql: SQL query to execute
            limit: Optional limit override
            
        Returns:
            Dictionary with results, metadata, and execution info
        """
        start_time = datetime.now()
        
        try:
            # Validate query safety
            is_valid, error_msg, warnings = self.safety_validator.validate_query(sql)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Query validation failed: {error_msg}",
                    "sql": sql,
                    "execution_time": 0
                }
            
            # Sanitize query
            clean_sql = self.safety_validator.sanitize_query(sql)
            
            # Add LIMIT if not present and limit is specified
            if limit and 'LIMIT' not in clean_sql.upper():
                clean_sql = f"{clean_sql.rstrip(';')} LIMIT {limit}"
            elif not limit and 'LIMIT' not in clean_sql.upper():
                clean_sql = f"{clean_sql.rstrip(';')} LIMIT {self.default_limit}"
            
            # Execute query
            async with async_db_manager.get_session() as session:
                result = await session.execute(text(clean_sql))
                
                # Get column names
                columns = list(result.keys()) if hasattr(result, 'keys') else []
                
                # Fetch results
                rows = result.fetchall()
                
                # Convert to list of dictionaries
                results = []
                for row in rows:
                    row_dict = {}
                    for i, value in enumerate(row):
                        column_name = columns[i] if i < len(columns) else f"column_{i}"
                        
                        # Handle different data types
                        if isinstance(value, datetime):
                            row_dict[column_name] = value.isoformat()
                        elif isinstance(value, (dict, list)):
                            row_dict[column_name] = json.dumps(value)
                        else:
                            row_dict[column_name] = value
                    
                    results.append(row_dict)
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return {
                    "success": True,
                    "results": results,
                    "columns": columns,
                    "row_count": len(results),
                    "sql_executed": clean_sql,
                    "execution_time": round(execution_time, 3),
                    "warnings": warnings,
                    "query_info": self.safety_validator.get_query_info(clean_sql)
                }
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Query execution error: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "sql": sql,
                "execution_time": round(execution_time, 3)
            }
    
    async def execute_with_pagination(self, sql: str, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """
        Execute query with pagination support.
        
        Args:
            sql: SQL query to execute
            page: Page number (1-based)
            page_size: Number of results per page
            
        Returns:
            Dictionary with paginated results and metadata
        """
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Add pagination to SQL
        paginated_sql = f"{sql.rstrip(';')} LIMIT {page_size} OFFSET {offset}"
        
        # Execute paginated query
        result = await self.execute_query(paginated_sql)
        
        if not result["success"]:
            return result
        
        # Get total count (remove LIMIT/OFFSET for count query)
        count_sql = self._create_count_query(sql)
        count_result = await self.execute_query(count_sql)
        
        total_count = 0
        if count_result["success"] and count_result["results"]:
            total_count = count_result["results"][0].get("count", 0)
        
        # Calculate pagination metadata
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        result.update({
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1
            }
        })
        
        return result
    
    def _create_count_query(self, sql: str) -> str:
        """Create a COUNT query from the original SQL."""
        # Simple approach: wrap the original query in a subquery and count
        # This works for most SELECT queries
        return f"SELECT COUNT(*) as count FROM ({sql.rstrip(';')}) as count_query"
    
    async def get_sample_data(self, table_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        Get sample data from a table for exploration.
        
        Args:
            table_name: Name of the table
            limit: Number of sample rows
            
        Returns:
            Dictionary with sample data
        """
        sql = f"SELECT * FROM {table_name} LIMIT {limit}"
        return await self.execute_query(sql)
    
    async def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get information about a table (columns, types, etc.).
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table information
        """
        sql = f"""
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_name = '{table_name}'
        ORDER BY ordinal_position
        """
        return await self.execute_query(sql)
