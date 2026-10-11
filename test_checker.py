import csv
import hashlib
from pathlib import Path
import tempfile
import unittest
import checker

class CheckerTests(unittest.TestCase):
    def setUp(self):
        # Keep all temporary test data under this project, not the system temp.
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, rows, columns=("id", "source", "translation"), bom=False):
        p = self.root / name
        with p.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(rows)
        return p

    def check(self, old, new, ret, columns=("id","source","translation")):
        paths = [self.write("old.csv", old, columns),
                 self.write("new.csv", new, columns),
                 self.write("ret.csv", ret)]
        tables = [checker.read_table(p, r) for p,r in zip(paths,checker.ROLES)]
        return checker.analyze(tables), paths

    def test_six_categories_and_no_first_wins(self):
        result, _ = self.check(
            [("same","Start",""),("changed","Old",""),("gone","Gone",""),("dup","One",""),
             ("dup","Two",""),("missing","Missing","")],
            [("same","Start",""),("changed","New",""),("dup","One",""),("added","Add",""),
             ("missing","Missing","")],
            [("same","Start","开始"),("changed","Old","旧"),("gone","Gone","删除"),
             ("dup","One","一")])
        s = result["sections"]
        self.assertEqual([x["id"] for x in s["added"]], ["added"])
        self.assertEqual([x["id"] for x in s["deleted"]], ["gone"])
        self.assertEqual([x["id"] for x in s["changed"]], ["changed"])
        self.assertEqual([x["id"] for x in s["missing"]], ["added","missing"])
        self.assertEqual(len(s["duplicate"]), 1)
        self.assertEqual({x["id"] for x in s["risk"]}, {"changed","gone","dup"})
        self.assertEqual(result["eligible"], ["same"])

    def test_concurrent_translation_edit(self):
        r,_ = self.check([("x","Hi","旧")],[("x","Hi","当前")],[("x","Hi","返回")])
        self.assertIn("当前译文已被修改", r["sections"]["risk"][0]["reason"])

    def test_identical_concurrent_result_is_not_overwrite(self):
        r,_ = self.check([("x","Hi","旧")],[("x","Hi","当前")],[("x","Hi","当前")])
        self.assertEqual(r["eligible"], ["x"])

    def test_source_tampering_even_if_matches_current(self):
        r,_ = self.check([("x","Old","")],[("x","New","")],[("x","New","新")])
        self.assertIn("返回source", r["sections"]["risk"][0]["reason"])

    def test_unknown_and_new_returned_ids(self):
        r,_ = self.check([], [("new","N","")], [("new","N","新"),("unknown","U","未")])
        self.assertEqual(len(r["sections"]["risk"]),2)
        self.assertFalse(r["eligible"])

    def test_blank_translation_is_missing_and_risky(self):
        r,_ = self.check([("x","X","原译")],[("x","X","原译")],[("x","X"," \t")])
        self.assertEqual(len(r["sections"]["missing"]),1)
        self.assertEqual(len(r["sections"]["risk"]),1)

    def test_optional_target_column_discloses_limit(self):
        r,_ = self.check([("x","X")],[("x","X")],[("x","X","译")],("id","source"))
        self.assertEqual(len(r["notes"]),1)

    def test_duplicate_returned_id_is_not_eligible(self):
        r,_ = self.check([("x","X","")],[("x","X","")],[("x","X","一"),("x","X","二")])
        self.assertFalse(r["eligible"])
        self.assertEqual(r["skipped"],["x"])

    def test_bom_multiline_quotes_unicode_leading_zero_id(self):
        p = self.write("bom.csv",[("001",'你好,\n"世界"',"是")],bom=True)
        t = checker.read_table(p,"returned_translation")
        self.assertFalse(t.errors)
        self.assertEqual(t.rows["001"][0]["source"],'你好,\n"世界"')

    def test_whitespace_source_change_not_normalized(self):
        r,_=self.check([("x","Hi","")],[("x","Hi ","")],[("x","Hi","嗨")])
        self.assertEqual(len(r["sections"]["changed"]),1)

    def test_bad_inputs_do_not_produce_clean_analysis(self):
        for text in ["id,id,source\nx,x,y\n","id,source\nx\n","id,source\n ,x\n",
                     "id,source\nx,y,z\n","id,source\nx,\"unclosed",
                     "id ,source\nx,y\n","id,source\nx,\x00\n",""]:
            with self.subTest(text=text):
                p=self.root/"bad.csv";p.write_text(text,encoding="utf-8")
                t=checker.read_table(p,"old_source")
                self.assertTrue(t.errors)
                r=checker.analyze([t,t,t])
                self.assertTrue(r["errors"])
                self.assertFalse(r["eligible"])

    def test_invalid_encoding(self):
        p=self.root/"bad.csv";p.write_bytes(b"id,source\nx,\xff")
        self.assertTrue(checker.read_table(p,"old_source").errors)

    def test_html_escaping_and_no_network_script(self):
        r,paths=self.check([("<script>","<img src=x onerror=alert(1)>","")],
                           [("<script>","changed","")],[("<script>","x","=SUM(A1)")]
                          )
        doc=checker.render([checker.read_table(p,k) for p,k in zip(paths,checker.ROLES)],r)
        self.assertNotIn("<script>",doc)
        self.assertNotIn("<img ",doc)
        self.assertIn("&lt;img",doc)
        self.assertIn("default-src 'none'",doc)

    def test_inputs_unchanged_and_report_repeatable(self):
        _,paths=self.check([("x","X","")],[("x","X","")],[("x","X","译")])
        before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        out=self.root/"out.html";second=self.root/"second.html"
        self.assertEqual(checker.run(paths,out),0)
        self.assertEqual(checker.run(paths,second),0)
        self.assertEqual(out.read_bytes(),second.read_bytes())
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])

    def test_no_output_overwrite(self):
        _,paths=self.check([],[],[])
        out=self.root/"report.html";out.write_text("KEEP",encoding="utf-8")
        with self.assertRaises(ValueError):checker.run(paths,out)
        self.assertEqual(out.read_text(encoding="utf-8"),"KEEP")

    def test_no_input_alias_overwrite(self):
        _,paths=self.check([],[],[])
        alias=self.root/"alias.html"
        alias.hardlink_to(paths[0])
        before=paths[0].read_bytes()
        with self.assertRaises(ValueError):checker.run(paths,alias)
        self.assertEqual(paths[0].read_bytes(),before)

    def test_error_report_and_exit_code(self):
        _,paths=self.check([],[],[])
        paths[0].write_text("broken",encoding="utf-8")
        out=self.root/"err.html"
        self.assertEqual(checker.run(paths,out),2)
        self.assertIn("六项检查未完成",out.read_text(encoding="utf-8"))

    def test_missing_file_handled(self):
        t=checker.read_table(self.root/"not-here.csv","old_source")
        self.assertTrue(t.errors)

    def test_resource_limits(self):
        p=self.write("limits.csv",[("1","X",""),("2","Y","")])
        previous=checker.MAX_ROWS
        try:
            checker.MAX_ROWS=1
            self.assertTrue(checker.read_table(p,"old_source").errors)
        finally:checker.MAX_ROWS=previous
        previous=checker.MAX_BYTES
        try:
            checker.MAX_BYTES=5
            self.assertTrue(checker.read_table(p,"old_source").errors)
        finally:checker.MAX_BYTES=previous

if __name__ == "__main__":
    unittest.main(verbosity=2)

