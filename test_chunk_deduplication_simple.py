#!/usr/bin/env python3
"""
Simple test script for chunk deduplication fix.
Tests the critical functionality without complex dependencies.
"""

import sys
import logging
from datetime import datetime

# Add src to path
sys.path.insert(0, '/app')

from src.database.manager import DatabaseManager
from src.database.models import ChunkAnalysisResultTable, ArticleTable
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def test_1_no_duplicates_in_db():
    """Test 1: Verify no duplicates exist in database."""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: Verify No Existing Duplicates in Database")
    logger.info("="*80)
    
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Query for any duplicate chunks
        duplicates = db.query(
            ChunkAnalysisResultTable.article_id,
            ChunkAnalysisResultTable.model_version,
            ChunkAnalysisResultTable.chunk_start,
            ChunkAnalysisResultTable.chunk_end,
            func.count().label('count')
        ).group_by(
            ChunkAnalysisResultTable.article_id,
            ChunkAnalysisResultTable.model_version,
            ChunkAnalysisResultTable.chunk_start,
            ChunkAnalysisResultTable.chunk_end
        ).having(func.count() > 1).all()
        
        total_rows = db.query(func.count(ChunkAnalysisResultTable.id)).scalar()
        
        logger.info(f"Total chunk analysis rows: {total_rows}")
        
        if duplicates:
            logger.error(f"❌ FAILED: Found {len(duplicates)} duplicate chunk groups:")
            for dup in duplicates[:10]:
                logger.error(f"  Article {dup.article_id}, model={dup.model_version}, "
                           f"chunk {dup.chunk_start}-{dup.chunk_end}: {dup.count} copies")
            return False
        else:
            logger.info("✅ PASSED: No duplicates found in database")
            return True
            
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_2_unique_constraint_exists():
    """Test 2: Verify unique constraint exists on table."""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Verify Unique Constraint Exists")
    logger.info("="*80)
    
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        from sqlalchemy import text
        
        # Query pg_indexes to check for our constraint
        result = db.execute(text("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'chunk_analysis_results' 
            AND indexname = 'idx_unique_chunk_per_article_version'
        """)).fetchone()
        
        if result:
            logger.info(f"Index name: {result[0]}")
            logger.info(f"Index definition: {result[1]}")
            logger.info("✅ PASSED: Unique constraint exists")
            return True
        else:
            logger.error("❌ FAILED: Unique constraint not found")
            return False
            
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        return False
    finally:
        db.close()


def test_3_constraint_prevents_duplicates():
    """Test 3: Try to insert duplicate and verify it's blocked."""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Database Constraint Prevents Duplicate Insertion")
    logger.info("="*80)
    
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Find any existing chunk
        existing = db.query(ChunkAnalysisResultTable).first()
        if not existing:
            logger.warning("⚠️  No existing chunks found - skipping test")
            return True
        
        logger.info(f"Found existing chunk: article_id={existing.article_id}, "
                   f"model={existing.model_version}, "
                   f"chunk {existing.chunk_start}-{existing.chunk_end}")
        
        # Try to insert exact duplicate
        duplicate = ChunkAnalysisResultTable(
            article_id=existing.article_id,
            chunk_start=existing.chunk_start,
            chunk_end=existing.chunk_end,
            chunk_text="TEST DUPLICATE - SHOULD BE BLOCKED",
            model_version=existing.model_version,
            ml_prediction=True,
            ml_confidence=0.9,
            hunt_score=50.0,
            hunt_prediction=True
        )
        
        db.add(duplicate)
        
        try:
            db.commit()
            logger.error("❌ FAILED: Database allowed duplicate insertion!")
            # Clean up if somehow it got through
            db.rollback()
            return False
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e)
            if "idx_unique_chunk_per_article_version" in error_msg or "duplicate key" in error_msg:
                logger.info("✅ PASSED: Constraint correctly blocked duplicate")
                logger.info(f"Error message: {error_msg.split('DETAIL:')[0].strip()}")
                return True
            else:
                logger.error(f"❌ FAILED: Different integrity error: {error_msg}")
                return False
                
    except Exception as e:
        logger.error(f"❌ FAILED: Unexpected error: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def test_4_article_645_fixed():
    """Test 4: Verify article 645 (the reported bug) is fixed."""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: Verify Article 645 (Bug Report) Is Fixed")
    logger.info("="*80)
    
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Check article 645 per model version (different models are allowed to have same chunks)
        model_versions = db.query(
            ChunkAnalysisResultTable.model_version,
            func.count().label('total')
        ).filter(
            ChunkAnalysisResultTable.article_id == 645
        ).group_by(
            ChunkAnalysisResultTable.model_version
        ).all()
        
        logger.info(f"Article 645 has {len(model_versions)} model versions")
        
        all_good = True
        for mv in model_versions:
            unique = db.query(
                func.count(func.distinct(
                    func.concat(
                        ChunkAnalysisResultTable.chunk_start,
                        '-',
                        ChunkAnalysisResultTable.chunk_end
                    )
                ))
            ).filter(
                ChunkAnalysisResultTable.article_id == 645,
                ChunkAnalysisResultTable.model_version == mv.model_version
            ).scalar()
            
            logger.info(f"  Model '{mv.model_version}': {mv.total} rows, {unique} unique chunks")
            
            if mv.total != unique:
                logger.error(f"    ❌ Duplicates found!")
                all_good = False
        
        if all_good:
            logger.info("✅ PASSED: Article 645 has no duplicates (per model version)")
            return True
        else:
            logger.error("❌ FAILED: Article 645 still has duplicates")
            return False
            
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        return False
    finally:
        db.close()


def test_5_all_articles_unique():
    """Test 5: Verify all articles have unique chunks."""
    logger.info("\n" + "="*80)
    logger.info("TEST 5: Verify All Articles Have Unique Chunks")
    logger.info("="*80)
    
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Get articles with chunk analysis
        articles = db.query(
            ChunkAnalysisResultTable.article_id,
            ChunkAnalysisResultTable.model_version,
            func.count().label('total')
        ).group_by(
            ChunkAnalysisResultTable.article_id,
            ChunkAnalysisResultTable.model_version
        ).all()
        
        logger.info(f"Checking {len(articles)} article/model combinations...")
        
        problems = []
        for article in articles:
            # Count unique chunks for this article/model
            unique = db.query(
                func.count(func.distinct(
                    func.concat(
                        ChunkAnalysisResultTable.chunk_start,
                        '-',
                        ChunkAnalysisResultTable.chunk_end
                    )
                ))
            ).filter(
                ChunkAnalysisResultTable.article_id == article.article_id,
                ChunkAnalysisResultTable.model_version == article.model_version
            ).scalar()
            
            if article.total != unique:
                problems.append({
                    'article_id': article.article_id,
                    'model_version': article.model_version,
                    'total': article.total,
                    'unique': unique
                })
        
        if problems:
            logger.error(f"❌ FAILED: Found {len(problems)} articles with duplicates:")
            for prob in problems[:10]:
                logger.error(f"  Article {prob['article_id']} ({prob['model_version']}): "
                           f"{prob['total']} rows, {prob['unique']} unique")
            return False
        else:
            logger.info(f"✅ PASSED: All {len(articles)} article/model combinations have unique chunks")
            return True
            
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    """Run all tests."""
    logger.info("\n" + "="*80)
    logger.info("CHUNK DEDUPLICATION FIX - VERIFICATION TEST SUITE")
    logger.info("="*80)
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    tests = [
        ("No Duplicates in Database", test_1_no_duplicates_in_db),
        ("Unique Constraint Exists", test_2_unique_constraint_exists),
        ("Constraint Prevents Duplicates", test_3_constraint_prevents_duplicates),
        ("Article 645 Fixed", test_4_article_645_fixed),
        ("All Articles Have Unique Chunks", test_5_all_articles_unique),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            logger.error(f"\nTest '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("TEST SUMMARY")
    logger.info("="*80)
    
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{status}: {name}")
    
    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)
    
    logger.info(f"\n{'='*80}")
    if passed_count == total_count:
        logger.info(f"🎉 ALL TESTS PASSED: {passed_count}/{total_count}")
    else:
        logger.info(f"⚠️  TESTS FAILED: {passed_count}/{total_count} passed")
    logger.info(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())

