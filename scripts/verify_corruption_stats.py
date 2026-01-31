import asyncio

# Add project root to path
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.getcwd())

from src.database.async_manager import AsyncDatabaseManager


async def verify():
    print("Verifying corruption stats logic...")

    # Setup mock session and results
    mock_session = AsyncMock()

    # Mock the count query result
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    # Mock the examples query result
    mock_examples_result = MagicMock()
    mock_row = MagicMock()
    mock_row.id = 123
    mock_row.title = "Corrupted Article"
    mock_examples_result.fetchall.return_value = [mock_row]

    # Configure session.execute side effects
    mock_session.execute.side_effect = [mock_count_result, mock_examples_result]

    # Initialize manager
    manager = AsyncDatabaseManager()

    # Patch get_session
    with patch.object(manager, "get_session", MagicMock()) as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Execute method
        stats = await manager.get_corruption_stats()

        # Verify results
        print(f"Stats received: {stats}")

        if stats["corrupted_count"] != 1:
            print("❌ Count mismatch")
            sys.exit(1)

        if len(stats["examples"]) != 1:
            print("❌ Examples length mismatch")
            sys.exit(1)

        if stats["examples"][0]["id"] != 123:
            print("❌ Example ID mismatch")
            sys.exit(1)

        print("✅ Verification successful!")


if __name__ == "__main__":
    asyncio.run(verify())
