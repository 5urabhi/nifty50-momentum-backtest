"""Next-action contracts must never represent unavailable sources as downloadable."""
import unittest

from workstation_api import model_data_manager


class ModelActionTest(unittest.TestCase):
    def action(self, **attrs):
        plan={"mode":"historical","status":"insufficient","runnable":False,
              "can_download":False,"missing_to_target":75}
        plan.update(attrs)
        return model_data_manager.recommend_next_action(plan)

    def test_select_stock_before_source_extension(self):
        action=self.action(status="select_ticker",can_download=True)
        self.assertEqual(action["kind"],"select_stock")
        self.assertIn("stock",action["label"].lower())

    def test_download_only_when_real_source_is_extendable(self):
        action=self.action(can_download=True,missing_to_target=79)
        self.assertEqual(action["kind"],"download")
        self.assertIn("+20%",action["label"])
        self.assertIn("uncovered",action["detail"])
        self.assertEqual(self.action(can_download=True,missing_to_target=0)["kind"],"data_library")

    def test_ready_minimum_is_runnable_even_without_buffer(self):
        action=self.action(status="ready_minimum",runnable=True,missing_to_target=8)
        self.assertEqual(action["kind"],"run")
        self.assertIn("buffer",action["detail"])

    def test_provider_blocker_never_pretends_to_be_downloadable(self):
        action=self.action(download_explanation="Original dated TRI is required")
        self.assertEqual(action["kind"],"data_library")
        self.assertIn("TRI",action["detail"])

    def test_options_require_original_quote(self):
        action=self.action(mode="market",status="needs_quote",can_download=False)
        self.assertEqual(action["kind"],"option_quotes")
        self.assertIn("CSV",action["detail"])
        self.assertEqual(self.action(mode="market",runnable=True)["kind"],"run")

    def test_theory_does_not_claim_historical_source(self):
        action=self.action(mode="synthetic",runnable=True)
        self.assertEqual(action["kind"],"run")
        self.assertIn("assumed inputs",action["detail"])

    def test_dataset_selection_is_explicit(self):
        self.assertEqual(self.action(status="select_dataset")["kind"],"select_dataset")


if __name__ == "__main__":
    unittest.main()
