"""An unchanged consumer must see the new runtime's version after partial rebuild."""
import ast
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
JDK=ROOT.parent/'jdk25/Contents/Home/bin'

def generated_source(version):
    line=next(v.strip() for v in (ROOT/'build.gradle').read_text().splitlines() if v.strip().startswith('file.text = ') and 'EngineBuildVersion' in v)
    return ast.literal_eval(line.split('=',1)[1].strip()).replace('${project.runtime_engine_version}',version)

class VersionBindingTest(unittest.TestCase):
    def test_unchanged_consumer_reads_replacement_version_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);src=d/'EngineBuildVersion.java';src.write_text(generated_source('1.8.46'))
            consumer=d/'Consumer.java';consumer.write_text('package dev.twob2tkit.runtime.engine; public class Consumer { public static void main(String[] args) { System.out.print(EngineBuildVersion.VALUE); } }')
            subprocess.run([str(JDK/'javac'),'-d',str(d),str(src),str(consumer)],check=True,capture_output=True)
            def value():return subprocess.check_output([str(JDK/'java'),'-cp',str(d),'dev.twob2tkit.runtime.engine.Consumer'],text=True)
            self.assertEqual(value(),'1.8.46');cached=(d/'dev/twob2tkit/runtime/engine/Consumer.class').read_bytes()
            src.write_text(generated_source('1.8.47'));subprocess.run([str(JDK/'javac'),'-d',str(d),str(src)],check=True,capture_output=True)
            self.assertEqual(cached,(d/'dev/twob2tkit/runtime/engine/Consumer.class').read_bytes())
            self.assertEqual(value(),'1.8.47')
    def test_generated_version_is_not_a_compile_time_constant(self):
        self.assertIn('VALUE = version()',generated_source('1.8.47'))

if __name__=='__main__':unittest.main()
