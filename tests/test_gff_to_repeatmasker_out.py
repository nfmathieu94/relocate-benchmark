import tempfile
import unittest
from pathlib import Path

from pipeline.gff_to_repeatmasker_out import convert


class TestGffToRepeatMaskerOut(unittest.TestCase):
    def test_conversion_preserves_boundaries_names_and_strand(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.gff"
            output = root / "full.repeatmasker.out"
            source.write_text(
                "##gff-version 3\n"
                "Chr1\tRepeatMasker\tTransposon\t11\t20\t42\t-\t.\t"
                "ID=TE1;Target=SINE03_OS 2 11;Class=SINE;"
                "PercDiv=1.2;PercDel=0.0;PercIns=0.5;\n"
            )
            self.assertEqual(convert(source, output), 1)
            fields = output.read_text().splitlines()[2].split()
            self.assertEqual(len(fields), 15)
            self.assertEqual(fields[4:10], ["Chr1", "11", "20", "(0)", "C", "SINE03_OS"])
            self.assertEqual(fields[10], "SINE")
            # Reverse (C) records order the repeat columns "(left) end begin";
            # the legacy parser reads column 14 as an integer begin, so it must
            # not be "(0)" (Target 2..11 -> "(0) 11 2").
            self.assertEqual(fields[11:14], ["(0)", "11", "2"])

    def test_forward_strand_repeat_columns_are_begin_end_left(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.gff"
            output = root / "full.repeatmasker.out"
            source.write_text(
                "##gff-version 3\n"
                "Chr1\tRepeatMasker\tTransposon\t11\t20\t42\t+\t.\t"
                "ID=TE1;Target=SINE03_OS 2 11;Class=SINE;\n"
            )
            self.assertEqual(convert(source, output), 1)
            fields = output.read_text().splitlines()[2].split()
            self.assertEqual(fields[8], "+")
            self.assertEqual(fields[11:14], ["2", "11", "(0)"])
