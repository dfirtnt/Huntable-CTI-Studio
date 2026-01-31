#!/usr/bin/env python3
"""
Evaluate OS Detection models against manual test data with human ground truth.

Compares multiple models (Gemini, Sonnet 4.5, Haiku 4.5, ChatGPT4o, ChatGPT5.1, SEC-BERT)
against human classifications.
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.services.os_detection_service import OSDetectionService
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.utils.content_filter import ContentFilter

# Manual test data from user
MANUAL_TEST_DATA = [
    {
        "url": "https://isc.sans.edu/diary/rss/32484",
        "title": "Microsoft Office Russian Dolls",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://www.infosecurity-magazine.com/news/akira-ransomware-244m-in-illicit/",
        "title": "Akira Ransomware Haul Surpasses $244M in Illicit Proceeds",
        "gemini": "Mixed",
        "sonnet_4_5": "Mixed",
        "haiku_4_5": "Mixed",
        "chatgpt4o": "Mixed",
        "chatgpt5_1": "Mixed",
        "sec_bert": "Mixed",
        "human": "Mixed",
    },
    {
        "url": "https://www.bleepingcomputer.com/news/security/cisa-warns-of-akira-ransomware-linux-encryptor-targeting-nutanix-vms/",
        "title": "CISA warns of Akira ransomware Linux encryptor targeting Nutanix VMs",
        "gemini": "Mixed",
        "sonnet_4_5": "Mixed",
        "haiku_4_5": "Mixed",
        "chatgpt4o": "Linux",
        "chatgpt5_1": "Linux",
        "sec_bert": "Mixed",
        "human": "Mixed",
    },
    {
        "url": "https://blog.talosintelligence.com/kraken-ransomware-group/",
        "title": "Unleashing the Kraken ransomware group",
        "gemini": "Mixed",
        "sonnet_4_5": "Mixed",
        "haiku_4_5": "Mixed",
        "chatgpt4o": "Mixed",
        "chatgpt5_1": "Mixed",
        "sec_bert": "Mixed",
        "human": "Mixed",
    },
    {
        "url": "https://isc.sans.edu/diary/rss/32480",
        "title": "Formbook Delivered Through Multiple Scripts",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "",
        "chatgpt5_1": "Windows",
        "sec_bert": "Mixed",
        "human": "Windows",
    },
    {
        "url": "https://thehackernews.com/2025/11/amazon-uncovers-attacks-exploited-cisco.html",
        "title": "Amazon Uncovers Attacks Exploited Cisco ISE and Citrix NetScaler as Zero-Day Flaws",
        "gemini": "Other",
        "sonnet_4_5": "Other",
        "haiku_4_5": "Other",
        "chatgpt4o": "Other",
        "chatgpt5_1": "Other",
        "sec_bert": "Windows",
        "human": "Other",
    },
    {
        "url": "https://thehackernews.com/2025/11/whatsapp-malware-maverick-hijacks.html",
        "title": "WhatsApp Malware 'Maverick' Hijacks Browser Sessions to Target Brazil's Biggest Banks",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Other",
        "chatgpt5_1": "Mixed",
        "sec_bert": "Mixed",
        "human": "Windows",
    },
    {
        "url": "https://thehackernews.com/2025/11/gootloader-is-back-using-new-font-trick.html",
        "title": "GootLoader Is Back, Using a New Font Trick to Hide Malware on WordPress Sites",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://www.bleepingcomputer.com/news/security/how-a-cpu-spike-led-to-uncovering-a-ransomhub-ransomware-attack/",
        "title": "How a CPU spike led to uncovering a RansomHub ransomware attack",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://unit42.paloaltonetworks.com/authentication-coercion/",
        "title": "You Thought It Was Over? Authentication Coercion Keeps Evolving",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://www.recordedfuture.com/research/tag-144s-persistent-grip-on-south-american-organizations",
        "title": "TAG-144's Persistent Grip on South American Organizations",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Other",
        "sec_bert": "Mixed",
        "human": "Windows",
    },
    {
        "url": "https://www.security.com/threat-intelligence/ukraine-russia-attacks",
        "title": "Ukrainian organizations still heavily targeted by Russian attacks",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Mixed",
        "chatgpt5_1": "Other",
        "sec_bert": "Mixed",
        "human": "Windows",
    },
    {
        "url": "https://research.checkpoint.com/2025/under-the-pure-curtain-from-rat-to-builder-to-coder/",
        "title": "Under the Pure Curtain: From RAT to Builder to Coder",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Mixed",
        "human": "Windows",
    },
    {
        "url": "https://thedfirreport.com/2025/08/05/from-bing-search-to-ransomware-bumblebee-and-adaptixc2-deliver-akira/",
        "title": "From Bing Search to Ransomware: Bumblebee and AdaptixC2 Deliver Akira",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://www.picussecurity.com/resource/blog/crypto24-ransomware-uncovered-stealth-persistence-and-enterprise-scale-impact",
        "title": "Crypto24 Ransomware Uncovered: Stealth, Persistence, and Enterprise-Scale Impact",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://www.recordedfuture.com/blog/september-2025-cve-landscape",
        "title": "September 2025 CVE Landscape",
        "gemini": "Mixed",
        "sonnet_4_5": "Mixed",
        "haiku_4_5": "Mixed",
        "chatgpt4o": "Other",
        "chatgpt5_1": "Mixed",
        "sec_bert": "Mixed",
        "human": "Mixed",
    },
    {
        "url": "https://blog.talosintelligence.com/uncovering-qilin-attack-methods-exposed-through-multiple-cases/",
        "title": "Uncovering Qilin attack methods exposed through multiple cases",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Mixed",
        "chatgpt5_1": "Mixed",
        "sec_bert": "Windows",
        "human": "Windows",
    },
    {
        "url": "https://www.recordedfuture.com/blog/october-2025-cve-landscape",
        "title": "October 2025 CVE Landscape",
        "gemini": "Mixed",
        "sonnet_4_5": "Mixed",
        "haiku_4_5": "Mixed",
        "chatgpt4o": "Other",
        "chatgpt5_1": "Mixed",
        "sec_bert": "Windows",
        "human": "Mixed",
    },
    {
        "url": "https://www.elastic.co/security-labs/roningloader",
        "title": "RONINGLOADER: DragonBreath's New Path to PPL Abuse",
        "gemini": "Windows",
        "sonnet_4_5": "Windows",
        "haiku_4_5": "Windows",
        "chatgpt4o": "Windows",
        "chatgpt5_1": "Windows",
        "sec_bert": "Mixed",
        "human": "Windows",
    },
]


def normalize_os_label(label: str) -> str:
    """Normalize OS label for comparison."""
    if not label or label.strip() == "":
        return "Unknown"
    label_lower = label.lower().strip()
    if label_lower in ["windows", "windows"]:
        return "Windows"
    if label_lower in ["linux", "linux"]:
        return "Linux"
    if label_lower in ["macos", "mac os", "mac"]:
        return "MacOS"
    if label_lower in ["mixed", "multiple", "multi"]:
        return "Mixed"
    if label_lower in ["other", "others"]:
        return "Other"
    return "Unknown"


def calculate_accuracy(predictions: list[str], ground_truth: list[str]) -> float:
    """Calculate accuracy between predictions and ground truth."""
    if len(predictions) != len(ground_truth):
        return 0.0
    correct = sum(1 for p, g in zip(predictions, ground_truth) if normalize_os_label(p) == normalize_os_label(g))
    return correct / len(predictions) if predictions else 0.0


def calculate_confusion_matrix(predictions: list[str], ground_truth: list[str]) -> dict[str, dict[str, int]]:
    """Calculate confusion matrix."""
    matrix = defaultdict(lambda: defaultdict(int))
    for pred, truth in zip(predictions, ground_truth):
        pred_norm = normalize_os_label(pred)
        truth_norm = normalize_os_label(truth)
        matrix[truth_norm][pred_norm] += 1
    return dict(matrix)


async def run_secbert_detection(article_id: int, content: str, junk_filter_threshold: float = 0.8) -> dict[str, Any]:
    """Run SEC-BERT OS detection with junk filter."""

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        # Get workflow config
        trigger_service = WorkflowTriggerService(db_session)
        config_obj = trigger_service.get_active_config()
        agent_models = config_obj.agent_models if config_obj and config_obj.agent_models else {}
        embedding_model = agent_models.get("OSDetectionAgent_embedding", "ibm-research/CTI-BERT")
        fallback_model = agent_models.get("OSDetectionAgent_fallback")

        # Apply junk filter
        content_filter = ContentFilter()
        article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
        hunt_score = (
            article.article_metadata.get("threat_hunting_score", 0) if article and article.article_metadata else 0
        )

        filter_result = content_filter.filter_content(
            content, min_confidence=junk_filter_threshold, hunt_score=hunt_score, article_id=article_id
        )
        filtered_content = filter_result.filtered_content or content

        # Run OS detection
        os_service = OSDetectionService(model_name=embedding_model)
        result = await os_service.detect_os(
            content=filtered_content, use_classifier=True, use_fallback=True, fallback_model=fallback_model
        )

        return {
            "detected_os": result.get("operating_system", "Unknown"),
            "method": result.get("method", "unknown"),
            "confidence": result.get("confidence", "unknown"),
            "similarities": result.get("similarities"),
            "max_similarity": result.get("max_similarity"),
        }
    finally:
        db_session.close()


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate OS Detection models against manual test data")
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/evaluations/os_detection_manual_eval.json",
        help="Output path for evaluation results",
    )
    parser.add_argument("--junk-filter-threshold", type=float, default=0.8, help="Junk filter threshold (default: 0.8)")

    args = parser.parse_args()

    print("=" * 80)
    print("OS Detection Model Comparison Evaluation")
    print("=" * 80)
    print()

    # Map URLs to article IDs
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    url_to_id = {}
    try:
        for test_item in MANUAL_TEST_DATA:
            article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url == test_item["url"]).first()
            if article:
                url_to_id[test_item["url"]] = article.id
            else:
                print(f"⚠️  Article not found: {test_item['url']}")
    finally:
        db_session.close()

    print(f"Found {len(url_to_id)} articles in database")
    print()

    # Run SEC-BERT detection on all articles
    print("Running SEC-BERT OS detection (with 0.8 junk filter)...")
    print("-" * 80)

    secbert_results = {}
    for test_item in MANUAL_TEST_DATA:
        url = test_item["url"]
        if url not in url_to_id:
            continue

        article_id = url_to_id[url]
        db_session = db_manager.get_session()
        try:
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if article:
                result = await run_secbert_detection(article_id, article.content, args.junk_filter_threshold)
                secbert_results[url] = result
                print(f"  Article {article_id}: {result['detected_os']} ({result['method']}, {result['confidence']})")
        finally:
            db_session.close()

    print()

    # Prepare evaluation data
    evaluation_data = []
    all_predictions = {
        "gemini": [],
        "sonnet_4_5": [],
        "haiku_4_5": [],
        "chatgpt4o": [],
        "chatgpt5_1": [],
        "sec_bert": [],
        "human": [],
    }

    for test_item in MANUAL_TEST_DATA:
        url = test_item["url"]
        if url not in url_to_id:
            continue

        article_id = url_to_id[url]
        human_truth = normalize_os_label(test_item["human"])

        # Get SEC-BERT result
        secbert_pred = secbert_results.get(url, {}).get("detected_os", "Unknown")
        secbert_pred = normalize_os_label(secbert_pred)

        # Collect all predictions
        all_predictions["gemini"].append(normalize_os_label(test_item["gemini"]))
        all_predictions["sonnet_4_5"].append(normalize_os_label(test_item["sonnet_4_5"]))
        all_predictions["haiku_4_5"].append(normalize_os_label(test_item["haiku_4_5"]))
        all_predictions["chatgpt4o"].append(normalize_os_label(test_item["chatgpt4o"]))
        all_predictions["chatgpt5_1"].append(normalize_os_label(test_item["chatgpt5_1"]))
        all_predictions["sec_bert"].append(secbert_pred)
        all_predictions["human"].append(human_truth)

        evaluation_data.append(
            {
                "article_id": article_id,
                "url": url,
                "title": test_item["title"],
                "ground_truth_os": human_truth,
                "predictions": {
                    "gemini": normalize_os_label(test_item["gemini"]),
                    "sonnet_4_5": normalize_os_label(test_item["sonnet_4_5"]),
                    "haiku_4_5": normalize_os_label(test_item["haiku_4_5"]),
                    "chatgpt4o": normalize_os_label(test_item["chatgpt4o"]),
                    "chatgpt5_1": normalize_os_label(test_item["chatgpt5_1"]),
                    "sec_bert": secbert_pred,
                },
                "secbert_details": secbert_results.get(url, {}),
            }
        )

    # Calculate metrics for each model
    print("=" * 80)
    print("MODEL COMPARISON METRICS")
    print("=" * 80)
    print()

    model_names = ["gemini", "sonnet_4_5", "haiku_4_5", "chatgpt4o", "chatgpt5_1", "sec_bert"]
    model_display_names = {
        "gemini": "Gemini",
        "sonnet_4_5": "Claude Sonnet 4.5",
        "haiku_4_5": "Claude Haiku 4.5",
        "chatgpt4o": "ChatGPT-4o",
        "chatgpt5_1": "ChatGPT-5.1",
        "sec_bert": "SEC-BERT (0.8 junk filter)",
    }

    metrics = {}
    for model in model_names:
        if model == "sec_bert":
            # Use actual SEC-BERT results
            predictions = all_predictions[model]
        else:
            predictions = all_predictions[model]

        accuracy = calculate_accuracy(predictions, all_predictions["human"])
        confusion = calculate_confusion_matrix(predictions, all_predictions["human"])

        metrics[model] = {"accuracy": accuracy, "confusion_matrix": confusion, "total_articles": len(predictions)}

        print(f"{model_display_names[model]:<30} Accuracy: {accuracy:.1%}")

    print()
    print("=" * 80)
    print("CONFUSION MATRICES")
    print("=" * 80)
    print()

    for model in model_names:
        print(f"\n{model_display_names[model]}:")
        print("-" * 60)
        confusion = metrics[model]["confusion_matrix"]

        # Get all unique labels
        all_labels = set()
        for truth_label, preds in confusion.items():
            all_labels.add(truth_label)
            all_labels.update(preds.keys())

        all_labels = sorted(all_labels)

        # Print header
        header = "Truth\\Pred"
        print(f"{header:<15}", end="")
        for label in all_labels:
            print(f"{label:<15}", end="")
        print()

        # Print rows
        for truth_label in all_labels:
            print(f"{truth_label:<15}", end="")
            for pred_label in all_labels:
                count = confusion.get(truth_label, {}).get(pred_label, 0)
                print(f"{count:<15}", end="")
            print()

    # Detailed per-article comparison
    print()
    print("=" * 80)
    print("PER-ARTICLE COMPARISON")
    print("=" * 80)
    print()

    print(
        f"{'Article ID':<10} {'Human':<12} {'SEC-BERT':<12} {'Gemini':<12} {'Sonnet 4.5':<12} {'Haiku 4.5':<12} {'GPT-4o':<12} {'GPT-5.1':<12} {'Match':<8}"
    )
    print("-" * 100)

    for item in evaluation_data:
        article_id = item["article_id"]
        human = item["ground_truth_os"]
        secbert = item["predictions"]["sec_bert"]
        gemini = item["predictions"]["gemini"]
        sonnet = item["predictions"]["sonnet_4_5"]
        haiku = item["predictions"]["haiku_4_5"]
        gpt4o = item["predictions"]["chatgpt4o"]
        gpt51 = item["predictions"]["chatgpt5_1"]

        # Count matches
        matches = sum(
            [secbert == human, gemini == human, sonnet == human, haiku == human, gpt4o == human, gpt51 == human]
        )

        match_str = f"{matches}/6"

        print(
            f"{article_id:<10} {human:<12} {secbert:<12} {gemini:<12} {sonnet:<12} {haiku:<12} {gpt4o:<12} {gpt51:<12} {match_str:<8}"
        )

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = {
        "evaluation_date": str(Path(__file__).stat().st_mtime),
        "total_articles": len(evaluation_data),
        "junk_filter_threshold": args.junk_filter_threshold,
        "metrics": metrics,
        "evaluation_data": evaluation_data,
    }

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print()
    print("=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Results saved to: {output_path}")
    print("\n📊 Summary:")
    print(f"   Total articles: {len(evaluation_data)}")
    print(
        f"   Best model: {max(metrics.items(), key=lambda x: x[1]['accuracy'])[0]} ({max(m['accuracy'] for m in metrics.values()):.1%})"
    )
    print(f"   SEC-BERT accuracy: {metrics['sec_bert']['accuracy']:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
