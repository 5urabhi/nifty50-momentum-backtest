"""Guard the current local acceptance entrypoint against legacy UI regressions."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock

from scripts import local_acceptance


class LocalAcceptanceCurrentTests(TestCase):
    def test_main_defaults_to_current_workstation_not_streamlit(self):
        with mock.patch.object(local_acceptance, "run_complete_acceptance") as run, \
             mock.patch.object(local_acceptance, "_build_react") as build, \
             mock.patch.object(local_acceptance, "_doctor", return_value="not_ready") as doctor:
            local_acceptance.main([])
        run.assert_called_once_with(include_streamlit=False, include_legacy=False)
        build.assert_called_once_with()
        doctor.assert_called_once_with("data/research_v1", "config/research_multifactor.json")

    def test_legacy_streamlit_is_explicitly_opt_in(self):
        with mock.patch.object(local_acceptance, "run_complete_acceptance") as run, \
             mock.patch.object(local_acceptance, "_build_react"), \
             mock.patch.object(local_acceptance, "_doctor"):
            local_acceptance.main(["--legacy-streamlit"])
        run.assert_called_once_with(include_streamlit=True, include_legacy=False)

    def test_missing_original_market_sources_are_not_software_failure(self):
        status = SimpleNamespace(
            returncode=2,
            stdout="QUANTLAB DOCTOR: OK\\nHISTORICAL RESEARCH: NOT READY\\n",
        )
        with mock.patch.object(local_acceptance.subprocess, "run", return_value=status):
            actual=local_acceptance._doctor("data/research_v1","config/research_multifactor.json")
        self.assertEqual(actual, "not_ready")

    def test_unrelated_exit_two_is_not_silently_approved(self):
        status=SimpleNamespace(returncode=2,stdout="ERROR: report exists already")
        with mock.patch.object(local_acceptance.subprocess, "run",return_value=status):
            with self.assertRaisesRegex(RuntimeError,"doctor FAILED"):
                local_acceptance._doctor("data/research_v1","config/research_multifactor.json")

    def test_numerical_readiness_does_not_claim_independent_certification(self):
        status=SimpleNamespace(returncode=0,stdout="QUANTLAB DOCTOR: OK\\nHISTORICAL RESEARCH: READY")
        with mock.patch.object(local_acceptance.subprocess, "run",return_value=status):
            actual=local_acceptance._doctor("data/research_v1","config/research_multifactor.json")
        self.assertEqual(actual,"numerically_ready_not_certified")

    def test_frontend_build_failure_is_not_ignored(self):
        status=SimpleNamespace(returncode=1,stdout="TypeScript compilation failed")
        with mock.patch.object(local_acceptance.subprocess, "run",return_value=status):
            with self.assertRaisesRegex(RuntimeError,"React/TypeScript build FAILED"):
                local_acceptance._build_react()

    def test_launcher_runs_current_acceptance_after_frontend_setup(self):
        text=(Path(__file__).resolve().parents[1]/"scripts"/"start.sh").read_text()
        self.assertIn('scripts/local_acceptance.py --skip-build',text)
        self.assertLess(text.index('npm run build'),text.index('scripts/local_acceptance.py --skip-build'))
        self.assertNotIn('scripts/local_acceptance.py\n',text)
