import unittest

from Published_reviews.plot_acceptance import (
    accepted_reviewer_count,
    deduplicate_papers,
    primary_meta_accepts,
    primary_meta_decision,
    reviewer_score,
)


class AcceptanceParsingTest(unittest.TestCase):
    def test_reviewer_score_and_acceptance_count(self):
        row = {
            "reviewer_1_rating": "(4) Weak Accept — marginally above the acceptance threshold",
            "reviewer_2_rating": "(3) Weak Reject — marginally below the acceptance threshold",
            "reviewer_3_rating": "(6) Strong Accept — must be accepted due to excellence",
        }
        self.assertEqual(reviewer_score(row["reviewer_1_rating"]), 4)
        self.assertEqual(accepted_reviewer_count(row), 2)

    def test_empty_or_unrecognised_rating_is_not_accepting(self):
        self.assertIsNone(reviewer_score(""))
        self.assertEqual(accepted_reviewer_count({}), 0)

    def test_primary_meta_decision_is_taken_from_first_recommendation(self):
        text = (
            "Recommendation: Invite for Rebuttal Please respond. "
            "Post-rebuttal recommendation: Accept Justification(s): ..."
        )
        self.assertEqual(primary_meta_decision(text), "Invite for Rebuttal")
        self.assertFalse(primary_meta_accepts(text))
        self.assertEqual(primary_meta_decision("Recommendation: Provisional Accept ..."), "Accept")
        self.assertTrue(primary_meta_accepts("Recommendation: Accept ..."))
        self.assertEqual(primary_meta_decision("Recommendation: Reject ..."), "Other")

    def test_combined_rows_are_deduplicated_by_paper_url(self):
        rows = [
            {"paper_url": "https://example.test/a", "modality": "MRI"},
            {"paper_url": "https://example.test/a", "modality": "CT-XRay"},
            {"paper_url": "https://example.test/b", "modality": "MRI"},
        ]
        self.assertEqual(len(deduplicate_papers(rows)), 2)


if __name__ == "__main__":
    unittest.main()
