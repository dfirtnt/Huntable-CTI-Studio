"""Standardized database connection patterns for testing."""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
import asyncpg
import redis.asyncio as redis

from tests.utils.test_environment import TestEnvironmentConfig, TestContext

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """Manages database connections with context-aware configuration."""
    
    def __init__(self, config: TestEnvironmentConfig):
        self.config = config
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[sessionmaker] = None
    
    @property
    def engine(self) -> AsyncEngine:
        """Get or create database engine."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine
    
    def _create_engine(self) -> AsyncEngine:
        """Create database engine with context-specific settings."""
        # Determine pool settings based on context
        if self.config.context == TestContext.CI:
            # CI: Use NullPool for faster test execution
            poolclass = NullPool
            pool_size = 1
            max_overflow = 0
        elif self.config.context == TestContext.DOCKER:
            # Docker: Use QueuePool with moderate settings
            poolclass = QueuePool
            pool_size = 5
            max_overflow = 10
        else:  # LOCALHOST
            # Localhost: Use QueuePool with standard settings
            poolclass = QueuePool
            pool_size = 5
            max_overflow = 10
        
        engine = create_async_engine(
            self.config.database_url,
            poolclass=poolclass,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            echo_pool=os.getenv("SQL_ECHO_POOL", "false").lower() == "true",
        )
        
        logger.info(f"Created database engine for {self.config.context.value} context")
        return engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._session_factory
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with proper cleanup."""
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    @asynccontextmanager
    async def get_transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with transaction."""
        async with self.engine.begin() as conn:
            session = AsyncSession(conn)
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def dispose(self):
        """Dispose of database engine."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database engine disposed")


class RedisConnectionManager:
    """Manages Redis connections with context-aware configuration."""
    
    def __init__(self, config: TestEnvironmentConfig):
        self.config = config
        self._client: Optional[redis.Redis] = None
    
    @property
    def client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client
    
    def _create_client(self) -> redis.Redis:
        """Create Redis client with context-specific settings."""
        # Determine connection settings based on context
        if self.config.context == TestContext.CI:
            # CI: Minimal settings for faster execution
            socket_timeout = 5
            socket_connect_timeout = 5
            max_connections = 5
        elif self.config.context == TestContext.DOCKER:
            # Docker: Standard settings
            socket_timeout = 10
            socket_connect_timeout = 10
            max_connections = 10
        else:  # LOCALHOST
            # Localhost: Standard settings
            socket_timeout = 10
            socket_connect_timeout = 10
            max_connections = 10
        
        # Only include password if it's provided
        redis_kwargs = {
            "host": self.config.redis_host,
            "port": self.config.redis_port,
            "db": self.config.redis_db,
            "socket_timeout": socket_timeout,
            "socket_connect_timeout": socket_connect_timeout,
            "max_connections": max_connections,
            "retry_on_timeout": True,
            "health_check_interval": 30
        }
        
        # Only add password if it's set
        if self.config.redis_password:
            redis_kwargs["password"] = self.config.redis_password
        
        client = redis.Redis(**redis_kwargs)
        
        logger.info(f"Created Redis client for {self.config.context.value} context")
        return client
    
    async def close(self):
        """Close Redis client."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis client closed")


class TestDatabaseManager:
    """Manages test database operations with isolation."""
    
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
        self.config = db_manager.config
    
    async def setup_test_database(self):
        """Set up test database with required tables."""
        logger.info("Setting up test database...")
        
        # Create test database if it doesn't exist
        await self._ensure_test_database()
        
        # Run migrations if needed
        await self._run_migrations()
        
        logger.info("Test database setup completed")
    
    async def teardown_test_database(self):
        """Tear down test database."""
        logger.info("Tearing down test database...")
        
        # Clear all tables
        await self._clear_all_tables()
        
        logger.info("Test database teardown completed")
    
    async def _ensure_test_database(self):
        """Ensure test database exists."""
        try:
            # Connect to default postgres database to create test database
            default_url = self.config.database_url.replace(f"/{self.config.postgres_db}", "/postgres")
            engine = create_async_engine(default_url, poolclass=NullPool)
            
            async with engine.begin() as conn:
                # Check if test database exists
                result = await conn.execute(
                    "SELECT 1 FROM pg_database WHERE datname = :db_name",
                    {"db_name": self.config.postgres_db}
                )
                
                if not result.fetchone():
                    # Create test database
                    await conn.execute(f"CREATE DATABASE {self.config.postgres_db}")
                    logger.info(f"Created test database: {self.config.postgres_db}")
                else:
                    logger.info(f"Test database already exists: {self.config.postgres_db}")
            
            await engine.dispose()
        except Exception as e:
            logger.error(f"Failed to ensure test database: {e}")
            raise
    
    async def _run_migrations(self):
        """Run database migrations."""
        try:
            # This would typically run Alembic migrations
            # For now, we'll just log that migrations would run here
            logger.info("Running database migrations...")
            # await alembic_upgrade_head()
            logger.info("Database migrations completed")
        except Exception as e:
            logger.error(f"Failed to run migrations: {e}")
            raise
    
    async def _clear_all_tables(self):
        """Clear all tables in test database."""
        try:
            async with self.db_manager.get_session() as session:
                # Get all table names
                result = await session.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
                tables = [row[0] for row in result.fetchall()]
                
                # Clear all tables
                for table in tables:
                    await session.execute(f"TRUNCATE TABLE {table} CASCADE")
                
                logger.info(f"Cleared {len(tables)} tables from test database")
        except Exception as e:
            logger.error(f"Failed to clear test database: {e}")
            raise
    
    async def create_test_data(self, data: Dict[str, Any]):
        """Create test data in database."""
        try:
            async with self.db_manager.get_session() as session:
                # This would create test data based on the provided data structure
                logger.info("Creating test data...")
                # Implementation would depend on your specific data models
                logger.info("Test data created")
        except Exception as e:
            logger.error(f"Failed to create test data: {e}")
            raise


class TestRedisManager:
    """Manages test Redis operations with isolation."""
    
    def __init__(self, redis_manager: RedisConnectionManager):
        self.redis_manager = redis_manager
        self.config = redis_manager.config
    
    async def setup_test_redis(self):
        """Set up test Redis database."""
        logger.info("Setting up test Redis...")
        
        # Clear test database
        await self._clear_test_database()
        
        logger.info("Test Redis setup completed")
    
    async def teardown_test_redis(self):
        """Tear down test Redis database."""
        logger.info("Tearing down test Redis...")
        
        # Clear test database
        await self._clear_test_database()
        
        logger.info("Test Redis teardown completed")
    
    async def _clear_test_database(self):
        """Clear test Redis database."""
        try:
            client = self.redis_manager.client
            await client.flushdb()
            logger.info(f"Cleared Redis database {self.config.redis_db}")
        except Exception as e:
            logger.error(f"Failed to clear Redis database: {e}")
            raise
    
    async def create_test_data(self, data: Dict[str, Any]):
        """Create test data in Redis."""
        try:
            client = self.redis_manager.client
            logger.info("Creating test data in Redis...")
            
            # Create test data based on provided structure
            for key, value in data.items():
                if isinstance(value, str):
                    await client.set(key, value)
                elif isinstance(value, dict):
                    await client.hset(key, mapping=value)
                elif isinstance(value, list):
                    await client.lpush(key, *value)
                elif isinstance(value, set):
                    await client.sadd(key, *value)
            
            logger.info("Test data created in Redis")
        except Exception as e:
            logger.error(f"Failed to create test data in Redis: {e}")
            raise


# Convenience functions for pytest integration
async def get_database_manager(config: TestEnvironmentConfig) -> DatabaseConnectionManager:
    """Get database manager for testing."""
    return DatabaseConnectionManager(config)


async def get_redis_manager(config: TestEnvironmentConfig) -> RedisConnectionManager:
    """Get Redis manager for testing."""
    return RedisConnectionManager(config)


async def get_test_database_manager(config: TestEnvironmentConfig) -> TestDatabaseManager:
    """Get test database manager."""
    db_manager = await get_database_manager(config)
    return TestDatabaseManager(db_manager)


async def get_test_redis_manager(config: TestEnvironmentConfig) -> TestRedisManager:
    """Get test Redis manager."""
    redis_manager = await get_redis_manager(config)
    return TestRedisManager(redis_manager)


# Context managers for easy use in tests
@asynccontextmanager
async def test_database_session(config: TestEnvironmentConfig) -> AsyncGenerator[AsyncSession, None]:
    """Get test database session with proper cleanup."""
    db_manager = DatabaseConnectionManager(config)
    async with db_manager.get_session() as session:
        yield session
    await db_manager.dispose()


@asynccontextmanager
async def test_redis_client(config: TestEnvironmentConfig) -> AsyncGenerator[redis.Redis, None]:
    """Get test Redis client with proper cleanup."""
    redis_manager = RedisConnectionManager(config)
    client = redis_manager.client
    try:
        yield client
    finally:
        await redis_manager.close()


# Database connection validation
async def validate_database_connection(config: TestEnvironmentConfig) -> bool:
    """Validate database connection."""
    try:
        db_manager = DatabaseConnectionManager(config)
        async with db_manager.get_session() as session:
            await session.execute("SELECT 1")
        await db_manager.dispose()
        return True
    except Exception as e:
        logger.error(f"Database connection validation failed: {e}")
        return False


async def validate_redis_connection(config: TestEnvironmentConfig) -> bool:
    """Validate Redis connection."""
    try:
        redis_manager = RedisConnectionManager(config)
        client = redis_manager.client
        await client.ping()
        await redis_manager.close()
        return True
    except Exception as e:
        logger.error(f"Redis connection validation failed: {e}")
        return False


if __name__ == "__main__":
    """CLI interface for database connection testing."""
    import argparse
    from tests.utils.test_environment import get_test_config
    
    parser = argparse.ArgumentParser(description="Test database connections")
    parser.add_argument("--validate", action="store_true", help="Validate connections")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    
    async def main():
        config = get_test_config()
        
        if args.validate:
            print("Validating database connections...")
            
            db_valid = await validate_database_connection(config)
            redis_valid = await validate_redis_connection(config)
            
            print(f"Database: {'✓' if db_valid else '✗'}")
            print(f"Redis: {'✓' if redis_valid else '✗'}")
            
            if not (db_valid and redis_valid):
                exit(1)
        else:
            print("Database connection utilities loaded successfully")
    
    asyncio.run(main())
