"""
Query Safety Validator for SQL injection prevention and read-only enforcement.
"""

import re
import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class QuerySafetyValidator:
    """Validate SQL queries for safety and read-only enforcement."""
    
    # Allowed SQL keywords (read-only operations)
    ALLOWED_KEYWORDS = {
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN',
        'OUTER JOIN', 'ON', 'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'OFFSET',
        'DISTINCT', 'AS', 'AND', 'OR', 'NOT', 'IN', 'EXISTS', 'BETWEEN', 'LIKE',
        'ILIKE', 'IS NULL', 'IS NOT NULL', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
        'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'CAST', 'EXTRACT', 'DATE_TRUNC',
        'NOW', 'CURRENT_DATE', 'CURRENT_TIMESTAMP', 'INTERVAL', 'UNION', 'ALL'
    }
    
    # Forbidden SQL keywords (write operations)
    FORBIDDEN_KEYWORDS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE',
        'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'EXECUTE',
        'EXEC', 'CALL', 'DECLARE', 'SET', 'BEGIN', 'END', 'IF', 'WHILE',
        'FOR', 'LOOP', 'FUNCTION', 'PROCEDURE', 'TRIGGER', 'INDEX', 'VIEW'
    }
    
    # Dangerous patterns that could indicate SQL injection
    DANGEROUS_PATTERNS = [
        r';\s*(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER)',  # Statement chaining
        r'--',  # SQL comments
        r'/\*.*?\*/',  # Multi-line comments
        r'UNION\s+SELECT',  # Union-based injection
        r'OR\s+1\s*=\s*1',  # Always true conditions
        r'AND\s+1\s*=\s*1',  # Always true conditions
        r'EXEC\s*\(',  # Dynamic execution
        r'xp_',  # Extended procedures
        r'sp_',  # Stored procedures
        r'@@',  # System variables
        r'CHAR\s*\(',  # Character functions
        r'ASCII\s*\(',  # ASCII functions
        r'SUBSTRING\s*\(',  # String manipulation
        r'CONCAT\s*\(',  # String concatenation
    ]
    
    def validate_query(self, sql: str) -> Tuple[bool, str, List[str]]:
        """
        Validate SQL query for safety.
        
        Args:
            sql: SQL query to validate
            
        Returns:
            Tuple of (is_valid, error_message, warnings)
        """
        if not sql or not sql.strip():
            return False, "Empty query", []
        
        sql_upper = sql.upper().strip()
        warnings = []
        
        # Check for forbidden keywords
        forbidden_found = []
        for keyword in self.FORBIDDEN_KEYWORDS:
            if re.search(r'\b' + re.escape(keyword) + r'\b', sql_upper):
                forbidden_found.append(keyword)
        
        if forbidden_found:
            return False, f"Forbidden keywords found: {', '.join(forbidden_found)}", []
        
        # Check for dangerous patterns
        dangerous_found = []
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                dangerous_found.append(pattern)
        
        if dangerous_found:
            return False, f"Dangerous patterns detected: {', '.join(dangerous_found)}", []
        
        # Check if query starts with SELECT
        if not sql_upper.startswith('SELECT'):
            return False, "Query must start with SELECT", []
        
        # Check for suspicious string concatenation
        if re.search(r'\|\|', sql):
            warnings.append("String concatenation detected")
        
        # Check for dynamic SQL patterns
        if re.search(r'\$', sql):
            warnings.append("Dollar quoting detected")
        
        # Check for excessive complexity
        select_count = sql_upper.count('SELECT')
        if select_count > 5:
            warnings.append("Complex query with multiple SELECT statements")
        
        # Check for large LIMIT values
        limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        if limit_match:
            limit_value = int(limit_match.group(1))
            if limit_value > 1000:
                warnings.append(f"Large LIMIT value: {limit_value}")
        
        return True, "", warnings
    
    def sanitize_query(self, sql: str) -> str:
        """
        Basic query sanitization (remove comments, normalize whitespace).
        
        Args:
            sql: Raw SQL query
            
        Returns:
            Sanitized SQL query
        """
        # Remove SQL comments
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        # Normalize whitespace
        sql = re.sub(r'\s+', ' ', sql)
        sql = sql.strip()
        
        return sql
    
    def get_query_info(self, sql: str) -> Dict[str, Any]:
        """
        Extract information about the query.
        
        Args:
            sql: SQL query
            
        Returns:
            Dictionary with query information
        """
        sql_upper = sql.upper()
        
        # Count different elements
        select_count = sql_upper.count('SELECT')
        join_count = sql_upper.count('JOIN')
        where_count = sql_upper.count('WHERE')
        order_count = sql_upper.count('ORDER BY')
        group_count = sql_upper.count('GROUP BY')
        
        # Extract table names
        from_match = re.search(r'FROM\s+(\w+)', sql_upper)
        table_name = from_match.group(1) if from_match else None
        
        # Extract LIMIT value
        limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        limit_value = int(limit_match.group(1)) if limit_match else None
        
        return {
            "select_statements": select_count,
            "joins": join_count,
            "where_clauses": where_count,
            "order_clauses": order_count,
            "group_clauses": group_count,
            "main_table": table_name,
            "limit_value": limit_value,
            "query_length": len(sql),
            "complexity_score": select_count + join_count + where_count
        }
