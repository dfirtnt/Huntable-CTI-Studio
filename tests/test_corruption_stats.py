"""Test corruption statistics functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.async_manager import AsyncDatabaseManager


@pytest.mark.asyncio
async def test_get_corruption_stats():
    """Test getting corruption statistics."""

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
    # First call is count, second is examples
    mock_session.execute.side_effect = [mock_count_result, mock_examples_result]

    # Initialize manager
    manager = AsyncDatabaseManager()

    # Patch get_session to return our mock session
    with patch.object(manager, "get_session", MagicMock()) as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Execute method
        stats = await manager.get_corruption_stats()

        # Verify results
        assert stats["corrupted_count"] == 1
        assert len(stats["examples"]) == 1
        assert stats["examples"][0]["id"] == 123
        assert stats["examples"][0]["title"] == "Corrupted Article"

        # Verify queries were constructed (checking if calls were made)
        assert mock_session.execute.call_count == 2
