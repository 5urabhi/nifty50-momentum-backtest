"""Read-only exact duplicate prepared dataset audit, no destructive data migration."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from workstation_api import source_inventory, service, research_library


class DuplicateScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="quantlab_duplicates_")
        self.base = Path(self.temp.name)
        self.paths = {}
        for name in ("upload_first", "upload_second", "upload_different"):
            folder = self.base / name
            folder.mkdir()
            self.paths[name] = folder
            (folder / "prices.csv").write_text(
                "date,STOCK\n2026-01-01,100\n2026-02-01,105\n"
                if name != "upload_different"
                else "date,STOCK\n2026-01-01,100\n2026-02-01,125\n")
            (folder / "membership.csv").write_text(
                "date,ticker,eligible\n2026-01-01,STOCK,True\n")
        self.records = [
            {"id": name, "label": name} for name in self.paths
        ] + [{"id": "dhan_shared", "label": "protected market originals"}]

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_byte_identical_groups_reported_only(self):
        def dataset_path(name):
            return self.paths[name], {"id": name, "label": name}
        with patch.object(service, "datasets", return_value=self.records), \
             patch.object(service, "dataset_path", side_effect=dataset_path), \
             patch.object(research_library, "resource_dependencies",
                          side_effect=lambda kind, id: [{"kind": "study", "id": "dependent"}]
                          if id == "upload_second" else []):
            result = source_inventory.scan()
        self.assertEqual(result["scanned_dataset_views"], 3)
        self.assertEqual(len(result["identical_groups"]), 1)
        match = result["identical_groups"][0]
        self.assertEqual({item["dataset_id"] for item in match["datasets"]},
                         {"upload_first", "upload_second"})
        self.assertTrue(all(item["protected_raw_market_cache"]
                            for item in match["datasets"]))
        self.assertEqual(next(x for x in match["datasets"]
                              if x["dataset_id"] == "upload_second")["dependencies"], 1)
        self.assertGreater(match["potential_view_bytes_reclaimable"], 0)
        for name, folder in self.paths.items():
            self.assertTrue((folder / "prices.csv").exists(), name)

    def test_different_exact_bytes_are_not_duplicates(self):
        (self.paths["upload_second"] / "membership.csv").write_text(
            "date,ticker,eligible\n2026-01-01,STOCK,False\n")
        with patch.object(service, "datasets", return_value=self.records), \
             patch.object(service, "dataset_path", side_effect=lambda name:
                          (self.paths[name], {})), \
             patch.object(research_library, "resource_dependencies", return_value=[]):
            result = source_inventory.scan()
        self.assertEqual(result["identical_groups"], [])
        self.assertEqual(len(result["skipped"]), 0)

    def test_symlink_sources_are_not_implicitly_deduplicated(self):
        target = self.paths["upload_first"] / "prices.csv"
        link = self.paths["upload_second"] / "prices.csv"
        link.unlink()
        link.symlink_to(target)
        with patch.object(service, "datasets", return_value=self.records), \
             patch.object(service, "dataset_path", side_effect=lambda name:
                          (self.paths[name], {})), \
             patch.object(research_library, "resource_dependencies", return_value=[]):
            result = source_inventory.scan()
        self.assertTrue(any(x["dataset_id"] == "upload_second"
                            for x in result["skipped"]))
        self.assertEqual(result["identical_groups"], [])


    def test_provenance_and_nested_files_must_match_before_cleanup(self):
        (self.paths["upload_second"]/"BENCHMARK_SOURCE.json").write_text('{"is_total_return":false}')
        def path_for(name):
            return self.paths[name],{"id":name,"label":name}
        with patch.object(service,"datasets",return_value=self.records), \\
             patch.object(service,"dataset_path",side_effect=path_for), \\
             patch.object(research_library,"resource_dependencies",return_value=[]):
            self.assertEqual(source_inventory.scan()["identical_groups"], [])
        (self.paths["upload_second"]/"BENCHMARK_SOURCE.json").unlink()
        folder=self.paths["upload_second"]/"daily_ohlcv"
        folder.mkdir()
        (folder/"SECURITY_A.csv").write_text("date,close\\n2026-01-01,99\\n")
        with patch.object(service,"datasets",return_value=self.records), \\
             patch.object(service,"dataset_path",side_effect=path_for), \\
             patch.object(research_library,"resource_dependencies",return_value=[]):
            self.assertEqual(source_inventory.scan()["identical_groups"], [])

    def test_only_confirmed_redundant_view_enters_recoverable_trash(self):
        def path_for(name):
            return self.paths[name],{"id":name,"label":name}
        with patch.object(service,"datasets",return_value=self.records), \\
             patch.object(service,"dataset_path",side_effect=path_for), \\
             patch.object(research_library,"resource_dependencies",return_value=[]), \\
             patch.object(research_library,"resource_action",
                          return_value={"trashed":True}) as action:
            report=source_inventory.scan()
            key=report["identical_groups"][0]["signature_sha256"]
            with self.assertRaisesRegex(ValueError,"Confirm"):
                source_inventory.trash_exact_duplicate("upload_second",key)
            with self.assertRaisesRegex(ValueError,"canonical"):
                source_inventory.trash_exact_duplicate("upload_first",key,confirm=True)
            result=source_inventory.trash_exact_duplicate("upload_second",key,confirm=True)
            self.assertEqual(result["source_preserved"],"upload_first")
            self.assertTrue(result["original_dhan_cache_untouched"])
            action.assert_called_once_with("dataset","upload_second","trash",confirm=True)
            (self.paths["upload_second"]/"prices.csv").write_text("date,STOCK\\n2026-01-01,1\\n")
            with self.assertRaisesRegex(ValueError,"changed"):
                source_inventory.trash_exact_duplicate("upload_second",key,confirm=True)
            action.assert_called_once()

    def test_cleanup_blocks_saved_dependents_even_for_identical_files(self):
        def path_for(name):
            return self.paths[name],{"id":name,"label":name}
        with patch.object(service,"datasets",return_value=self.records), \\
             patch.object(service,"dataset_path",side_effect=path_for), \\
             patch.object(research_library,"resource_dependencies",
                          side_effect=lambda kind, name: [{"kind":"study","id":"locked"}]
                          if name=="upload_second" else []), \\
             patch.object(research_library,"resource_action") as action:
            key=source_inventory.scan()["identical_groups"][0]["signature_sha256"]
            with self.assertRaisesRegex(ValueError,"Saved studies"):
                source_inventory.trash_exact_duplicate("upload_second",key,confirm=True)
            action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
