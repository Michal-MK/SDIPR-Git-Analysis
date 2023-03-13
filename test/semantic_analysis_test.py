import unittest
from pathlib import Path

from environment import TURTLE_GRAPHICS_REPO
from lib import get_tracked_files
from semantic_analysis import compute_semantic_weight


class SemanticsAnalyzerTest(unittest.TestCase):

    def test_semantic_weight_tg(self):
        weights = []
        file_groups = get_tracked_files(Path(TURTLE_GRAPHICS_REPO))
        for group in file_groups:
            for file in group.files:
                print(file)
                if file.suffix == ".cs":
                    _, weight = compute_semantic_weight(file.absolute())
                    weights.append(weight)
        pass

    def test_semantic_weight_single_file(self):
        weights = []
        file_groups = get_tracked_files(Path('../repositories/single_file'))
        for group in file_groups:
            for file in group.files:
                print(file)
                if file.suffix == ".cs":
                    _, weight = compute_semantic_weight(file.absolute())
                    weights.append(weight)
        self.assertTrue(len(weights) == 1)
        self.assertTrue(weights[0] == 38.0)

if __name__ == '__main__':
    unittest.main()