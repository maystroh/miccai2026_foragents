import tempfile
import unittest
from pathlib import Path

from Published_papers.parse_mri_category import extract_rows


class CategoryParserTest(unittest.TestCase):
    def test_extracts_only_papers_in_mri_section(self):
        html = """
        <h3>Applications -&gt; MRI</h3>
        <ul><li><a href="/miccai-2026/9999-Paper1111.html">Wrong section</a></li></ul>
        <h3>Modalities -&gt; MRI</h3>
        <ul>
          <li><a href="/miccai-2026/0002-Paper5533.html">First paper</a></li>
          <li><a href="/miccai-2026/0003-Paper4553.html">Second paper</a></li>
          <li><a href="/miccai-2026/0003-Paper4553.html">Second paper</a></li>
        </ul>
        <h3>Modalities -&gt; CT</h3>
        <ul><li><a href="/miccai-2026/0004-Paper9999.html">Wrong modality</a></li></ul>
        """
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "categories.html"
            source.write_text(html, encoding="utf-8")
            rows = extract_rows(str(source), "Modalities -> MRI")

        self.assertEqual(
            rows,
            [
                {"title": "First paper", "paper_url": "file:///miccai-2026/0002-Paper5533.html"},
                {"title": "Second paper", "paper_url": "file:///miccai-2026/0003-Paper4553.html"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
