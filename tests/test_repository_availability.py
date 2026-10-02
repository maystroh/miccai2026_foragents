"""Regression checks for corpus denominators and link interpretation."""

import unittest

from src.repository_availability import abstract_repository_links, classify_link, modality_summaries, summarize


class RepositoryAvailabilityTests(unittest.TestCase):
    def test_multimodal_paper_counts_once_overall_and_once_in_each_modality(self):
        rows = [
            {"original_modalities": "CT-XRay | MRI", "retained_modality": "CT-XRay",
             "link_type": "repository_host_link", "public_access_status": "not_checked"},
            {"original_modalities": "MRI", "retained_modality": "MRI",
             "link_type": "no_listed_link", "public_access_status": "no_listed_link"},
        ]
        stats = {row["modality"]: row for row in modality_summaries(rows)}
        self.assertEqual(summarize(rows, "overall")["papers"], 2)
        self.assertEqual(stats["MRI"]["papers"], 2)
        self.assertEqual(stats["MRI"]["listed_code_link_percent"], 50)
        self.assertEqual(stats["CT-XRay"]["papers"], 1)
        retained = {row["modality"]: row for row in modality_summaries(rows, original=False)}
        self.assertEqual(retained["MRI"]["papers"], 1)

    def test_project_and_data_links_do_not_count_as_repository_links(self):
        self.assertEqual(classify_link("https://team.github.io/project/"), "project_page")
        self.assertEqual(classify_link("https://huggingface.co/datasets/team/data"), "model_or_dataset_hub")
        self.assertEqual(classify_link("https://github.com/team/project/tree/main"), "repository_host_link")
        self.assertEqual(classify_link("https://anonymous.4open.science/r/project-A123"), "anonymous_repository_link")
        self.assertEqual(classify_link("  "), "no_listed_link")

    def test_http_accessibility_does_not_follow_from_listed_link(self):
        rows = [{"link_type": "repository_host_link", "public_access_status": "network_error"}]
        summary = summarize(rows, "overall")
        self.assertEqual(summary["repository_host_links"], 1)
        self.assertEqual(summary["accessible_repository_pages"], 0)
        self.assertEqual(summary["unresolved_link_checks"], 1)

    def test_abstract_link_recovery_removes_prose_punctuation_and_preserves_git_suffix(self):
        self.assertEqual(
            abstract_repository_links(r"Code: \url{https://github.com/team/repo.git}. Data: https://zenodo.org/records/1."),
            ["https://github.com/team/repo.git"],
        )
        self.assertEqual(abstract_repository_links("See (https://github.com/team/repo)."), ["https://github.com/team/repo"])


if __name__ == "__main__":
    unittest.main()
