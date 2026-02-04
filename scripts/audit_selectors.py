#!/usr/bin/env python3
"""
Audit script to compare test selectors with HTML template elements.
Generates a comprehensive report of mismatches.
"""

import glob
import re
from collections import defaultdict
from pathlib import Path

# Run from project root (script may be in scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def extract_test_selectors():
    """Extract all selectors used in test files."""
    test_files = glob.glob(str(PROJECT_ROOT / "tests/ui/test_*.py"))
    selectors = defaultdict(lambda: {"files": set(), "count": 0})

    for test_file in test_files:
        try:
            with open(test_file) as f:
                content = f.read()
                file_name = Path(test_file).name

                # Pattern: page.locator("#id") or page.locator(".class")
                locator_pattern = r'locator\(["\']([#.][\w-]+)["\']\)'
                matches = re.findall(locator_pattern, content)
                for match in matches:
                    selectors[match]["files"].add(file_name)
                    selectors[match]["count"] += 1

                # Pattern: getElementById("id")
                get_element_pattern = r'getElementById\(["\']([\w-]+)["\']\)'
                matches = re.findall(get_element_pattern, content)
                for match in matches:
                    selector = f"#{match}"
                    selectors[selector]["files"].add(file_name)
                    selectors[selector]["count"] += 1

                # Pattern: querySelector("#id") or querySelector(".class")
                query_pattern = r'querySelector\(["\']([#.][\w-]+)["\']\)'
                matches = re.findall(query_pattern, content)
                for match in matches:
                    selectors[match]["files"].add(file_name)
                    selectors[match]["count"] += 1

        except Exception as e:
            print(f"Error reading {test_file}: {e}")

    return selectors


def extract_template_elements():
    """Extract all IDs and classes from HTML templates."""
    html_files = glob.glob(str(PROJECT_ROOT / "src/web/templates/*.html"))
    template_ids = set()
    template_classes = set()
    id_to_file = defaultdict(set)
    class_to_file = defaultdict(set)

    for html_file in html_files:
        try:
            with open(html_file) as f:
                content = f.read()
                file_name = Path(html_file).name

                # Extract IDs
                id_pattern = r'id=["\']([\w-]+)["\']'
                ids = re.findall(id_pattern, content)
                for id_val in ids:
                    template_ids.add(id_val)
                    id_to_file[id_val].add(file_name)

                # Extract classes
                class_pattern = r'class=["\']([^"\']+)["\']'
                class_strings = re.findall(class_pattern, content)
                for class_str in class_strings:
                    classes = class_str.split()
                    for cls in classes:
                        template_classes.add(cls)
                        class_to_file[cls].add(file_name)

        except Exception as e:
            print(f"Error reading {html_file}: {e}")

    return {"ids": template_ids, "classes": template_classes, "id_to_file": id_to_file, "class_to_file": class_to_file}


def audit_selectors():
    """Main audit function."""
    print("=" * 80)
    print("SELECTOR AUDIT: Tests vs Templates")
    print("=" * 80)

    # Extract data
    print("\n[1/4] Extracting selectors from test files...")
    test_selectors = extract_test_selectors()
    print(f"   Found {len(test_selectors)} unique selectors in tests")

    print("\n[2/4] Extracting elements from HTML templates...")
    templates = extract_template_elements()
    print(f"   Found {len(templates['ids'])} IDs in templates")
    print(f"   Found {len(templates['classes'])} unique classes in templates")

    # Compare
    print("\n[3/4] Comparing selectors...")
    missing_ids = []
    missing_classes = []
    found_ids = []
    found_classes = []

    for selector, info in test_selectors.items():
        if selector.startswith("#"):
            # ID selector
            id_name = selector[1:]  # Remove #
            if id_name in templates["ids"]:
                found_ids.append((selector, info, templates["id_to_file"][id_name]))
            else:
                missing_ids.append((selector, info))
        elif selector.startswith("."):
            # Class selector
            class_name = selector[1:]  # Remove .
            if class_name in templates["classes"]:
                found_classes.append((selector, info, templates["class_to_file"][class_name]))
            else:
                missing_classes.append((selector, info))

    # Generate report
    print("\n[4/4] Generating report...")
    print("\n" + "=" * 80)
    print("AUDIT RESULTS")
    print("=" * 80)

    print(f"\n✅ FOUND: {len(found_ids) + len(found_classes)} selectors")
    print(f"   - IDs: {len(found_ids)}")
    print(f"   - Classes: {len(found_classes)}")

    print(f"\n❌ MISSING: {len(missing_ids) + len(missing_classes)} selectors")
    print(f"   - IDs: {len(missing_ids)}")
    print(f"   - Classes: {len(missing_classes)}")

    # Detailed missing report
    if missing_ids:
        print("\n" + "-" * 80)
        print("MISSING ID SELECTORS (High Priority)")
        print("-" * 80)
        for selector, info in sorted(missing_ids, key=lambda x: -x[1]["count"]):
            files = ", ".join(sorted(info["files"]))
            print(f"\n  {selector} (used {info['count']} times)")
            print(f"    Files: {files}")

    if missing_classes:
        print("\n" + "-" * 80)
        print("MISSING CLASS SELECTORS (Medium Priority)")
        print("-" * 80)
        for selector, info in sorted(missing_classes, key=lambda x: -x[1]["count"])[:20]:  # Top 20
            files = ", ".join(sorted(info["files"]))
            print(f"\n  {selector} (used {info['count']} times)")
            print(f"    Files: {files}")
        if len(missing_classes) > 20:
            print(f"\n  ... and {len(missing_classes) - 20} more class selectors")

    # Save detailed report
    report_dir = PROJECT_ROOT / "test-results"
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / "selector_audit_report.txt"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("SELECTOR AUDIT REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total test selectors: {len(test_selectors)}\n")
        f.write(f"Found in templates: {len(found_ids) + len(found_classes)}\n")
        f.write(f"Missing from templates: {len(missing_ids) + len(missing_classes)}\n\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("MISSING ID SELECTORS\n")
        f.write("=" * 80 + "\n\n")
        for selector, info in sorted(missing_ids, key=lambda x: -x[1]["count"]):
            f.write(f"{selector} (used {info['count']} times)\n")
            f.write(f"  Files: {', '.join(sorted(info['files']))}\n\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("MISSING CLASS SELECTORS\n")
        f.write("=" * 80 + "\n\n")
        for selector, info in sorted(missing_classes, key=lambda x: -x[1]["count"]):
            f.write(f"{selector} (used {info['count']} times)\n")
            f.write(f"  Files: {', '.join(sorted(info['files']))}\n\n")

    print(f"\n📄 Detailed report saved to: {report_file}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    audit_selectors()
