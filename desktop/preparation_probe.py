"""Exercise installed preparation tools using fictional records, without network access."""
import csv
import json
import os
from pathlib import Path
import subprocess


def check(runtime, work, env):
    work.mkdir(parents=True)
    runtime = Path(runtime)

    def run(tool, *args):
        command = [str(runtime / "bin" / tool)]
        if os.name == "nt":
            command.insert(0, str(runtime / "perl/bin/perl.exe"))
        return subprocess.check_output([*command, *map(str, args)], cwd=work, env=env,
                                       text=True, stderr=subprocess.STDOUT, timeout=120)

    for tool, version in (("convert-pheno", "0.35"), ("clarid-tools", "0.04")):
        if run(tool, "--version").strip().split()[-1] != version:
            raise RuntimeError(f"Unexpected {tool} version")
    source = work / "clinical.csv"
    source.write_text("id,sex,diagnosis,pasi\nTEST-1,Female,Psoriasis,7.5\n", encoding="utf-8")
    mapping = work / "clinical.yaml"
    mapping.write_text('''mappingVersion: 2
source: {profile: csv}
target: {model: beacon, schemaVersion: '2.0.0'}
project: {id: packaging-test, version: '0.1'}
defaults: {ontology: ncit}
records: {}
beacon:
  individuals:
    id: {sourceFields: [id], primaryKey: id}
    sex: {sourceField: sex, query: {from: value}}
    diseases:
      rules:
        - sourceField: diagnosis
          diseaseCode: {query: Psoriasis}
    measures:
      rules:
        - sourceField: pasi
          assayCode: {query: Psoriasis Area and Severity Index Clinical Classification}
          measurementValue:
            quantity:
              unit: {term: {id: 'UCUM:1', label: score}}
''', encoding="utf-8")
    output = work / "clinical.json"
    run("convert-pheno", "-icsv", source, "--separator", ",", "--mapping-file", mapping,
        "--search", "exact", "--no-source-info", "-obff", output)
    records = json.loads(output.read_text(encoding="utf-8"))
    if (len(records) != 1 or records[0]["id"] != "TEST-1"
            or records[0]["diseases"][0]["diseaseCode"]["id"] != "NCIT:C3346"
            or records[0]["measures"][0]["assayCode"]["id"] != "NCIT:C135734"
            or records[0]["measures"][0]["measurementValue"]["quantity"]["value"] != 7.5):
        raise RuntimeError("CSV-to-BFF terminology/value check failed")
    source = work / "subjects.csv"
    source.write_text("unique_id,subject_id,study,type,condition,sex,age_group\n"
                      "TEST-1,1,TEST,Case,L40.9,Not Available,Not Available\n", encoding="utf-8")
    # A local codebook extension exercises the same path used by Store builders.
    books = list((runtime / "perl").rglob("versions/0.04/clarid-codebook.yaml"))
    if len(books) != 1:
        raise RuntimeError("Expected one installed ClarID 0.04 codebook")
    codebook = work / "codebook.yaml"
    perl = runtime / ("perl/bin/perl.exe" if os.name == "nt" else "perl/bin/perl")
    codebook_env = dict(env)
    if os.sys.platform == "linux":
        codebook_env["LD_LIBRARY_PATH"] = str(runtime / "lib")
    subprocess.run([str(perl), "-MYAML::XS", "-e",
                    'my $b = YAML::XS::LoadFile($ARGV[0]); '
                    '$b->{entities}{subject}{study}{TEST} = '
                    '{code=>"TEST",stub_code=>"TST",label=>"Test",id=>"NCIT:C17998"}; '
                    'YAML::XS::DumpFile($ARGV[1], $b);', str(books[0]), str(codebook)],
                   cwd=work, env=codebook_env, check=True, timeout=30)
    for fmt, column in (("human", "clar_id"), ("stub", "stub_id")):
        encoded, decoded = work / f"{fmt}.csv", work / f"{fmt}-decoded.csv"
        base = ("code", "--entity", "subject", "--format", fmt, "--codebook", codebook, "--sep", ",")
        run("clarid-tools", *base, "--action", "encode", "--infile", source, "--outfile", encoded)
        with encoded.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        ids = work / f"{fmt}-ids.csv"
        with ids.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["unique_id", column])
            writer.writerow(["TEST-1", row[column]])
        run("clarid-tools", *base, "--action", "decode", "--infile", ids,
            "--outfile", decoded, "--with-condition-name")
        with decoded.open(newline="", encoding="utf-8") as handle:
            recovered = next(csv.DictReader(handle))
        if (int(recovered["subject_id"]) != 1 or recovered["condition"] != "L40.9"
                or recovered["condition_name"] != "Psoriasis, unspecified"
                or recovered["study"] != ("TEST" if fmt == "human" else "TST")):
            raise RuntimeError("ClarID round-trip check failed")
