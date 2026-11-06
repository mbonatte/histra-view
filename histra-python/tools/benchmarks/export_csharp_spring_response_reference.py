"""Run verbatim C# response getters in a small field-only .NET harness.

No solver or constitutive update is reproduced here. Source bodies come from
HiStrA's original Spring classes; the wrapper supplies controlled committed
fields and emits IEEE bit patterns, including undefined divisions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def _method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def _cases():
    base = dict(u=1.0, f=2.0, k=10.0, fy=[4.0, -6.0], ur=[2.0, -3.0], length=2.0)
    variations = [
        ('elastic', 1, {}), ('elastic_zero_length', 1, dict(length=0.0)),
        ('hysteretic_positive', 8, {}), ('hysteretic_negative', 8, dict(u=-1.0)),
        ('hysteretic_inside_yield', 8, dict(u=0.1)), ('hysteretic_at_yield', 8, dict(u=0.4)),
        ('hysteretic_unloading', 8, dict(u=0.1, f=-12.0)),
        ('hysteretic_zero_ur', 8, dict(ur=[0.0, 0.0])),
        ('hysteretic_unlimited_tension', 8, dict(ur=[100000.0, -3.0])),
        ('hysteretic_unlimited_compression', 8, dict(u=-1.0, ur=[2.0, -100000.0])),
        ('hysteretic_below_unlimited', 8, dict(ur=[99999.999, -3.0])),
        ('hysteretic_zero_length_initial', 8, dict(u=0.0, f=0.0, length=0.0)),
        ('hysteretic_zero_length_loaded', 8, dict(length=0.0)),
        ('hysteretic_zero_k', 8, dict(k=0.0)),
        ('coulomb_positive', 12, {}), ('coulomb_negative', 12, dict(u=-1.0, f=-2.0)),
        ('coulomb_opposite_sign_up', 12, dict(u=0.1, f=3.0)),
        ('coulomb_threshold_inside', 12, dict(u=0.200001)),
        ('coulomb_threshold_outside', 12, dict(u=0.20001)),
        ('coulomb_zero_ur', 12, dict(ur=[0.0, 0.0])),
        ('coulomb_zero_k', 12, dict(k=0.0, f=0.0)),
        ('coulomb_zero_length', 12, dict(length=0.0)),
        ('negative_zero', 12, dict(u=-0.0, f=0.0)),
        ('single_overflow', 8, dict(u=1e100, f=1e100)),
        ('single_rounding', 8, dict(u=1.23456789012345, length=3.141592653589793)),
    ]
    return [dict(name=name, kind=kind, phase=index % 11, **{**base, **change})
            for index, (name, kind, change) in enumerate(variations)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.source_root / 'ModelLibrary/Objects'
    paths = {name: root / f'Spring{name}.cs' for name in ('', 'Hysteretic', 'Coulomb03')}
    sources = {name: path.read_text(encoding='utf-8-sig') for name, path in paths.items()}
    signatures = ('public override double GetUp()', 'public override float GetStrainPlastic()',
                  'public override float GetUpOverUr()')
    base_methods = '\n'.join(_method(sources[''], s.replace('override', 'virtual')) for s in signatures)
    base_methods += '\n' + _method(sources[''], 'public virtual float GetStrain()')
    code = '''using System; using System.IO; using System.Text.Json; using System.Collections.Generic;
class Spring {
 protected double _u; protected double[] _fy = new double[2], _ur = new double[2];
 public double U {get=>_u;set=>_u=value;} public double F,K,Length;
 public void SetLimits(double[] fy,double[] ur){_fy=fy;_ur=ur;}
''' + base_methods + '\n}\n'
    for name in ('Hysteretic', 'Coulomb03'):
        code += f'class Spring{name}: Spring {{\n' + '\n'.join(_method(sources[name], s) for s in signatures) + '\n}\n'
    code += '''class Program {
 static string B32(float x)=>BitConverter.SingleToUInt32Bits(x).ToString("x8");
 static string B64(double x)=>BitConverter.DoubleToUInt64Bits(x).ToString("x16");
 static void Main(string[] args){
 var input=JsonDocument.Parse(File.ReadAllText(args[0])); var output=new List<object>();
 foreach(var c in input.RootElement.EnumerateArray()){
 int kind=c.GetProperty("kind").GetInt32(); Spring s=kind==8?new SpringHysteretic():kind==12?new SpringCoulomb03():new Spring();
 s.U=c.GetProperty("u").GetDouble();s.F=c.GetProperty("f").GetDouble();s.K=c.GetProperty("k").GetDouble();s.Length=c.GetProperty("length").GetDouble();
 s.SetLimits(JsonSerializer.Deserialize<double[]>(c.GetProperty("fy")),JsonSerializer.Deserialize<double[]>(c.GetProperty("ur")));
 output.Add(new {name=c.GetProperty("name").GetString(),strain=B32(s.GetStrain()),plastic_displacement=B64(s.GetUp()),plastic_strain=B32(s.GetStrainPlastic()),plastic_ratio=B32(s.GetUpOverUr())});
 }Console.WriteLine(JsonSerializer.Serialize(output));}}
'''
    cases = _cases()
    with tempfile.TemporaryDirectory(prefix='histra-spring-response-') as folder:
        work = Path(folder)
        (work / 'Oracle.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>disable</ImplicitUsings></PropertyGroup></Project>')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'Program.cs').write_text(code)
        (work / 'cases.json').write_text(json.dumps(cases))
        subprocess.run([args.dotnet, 'build', '-c', 'Release', '--configfile', str(work / 'NuGet.Config')], cwd=work, check=True, capture_output=True)
        output = subprocess.check_output([args.dotnet, str(work / 'bin/Release/net8.0/Oracle.dll'), str(work / 'cases.json')], text=True)
    result = {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'generator': str(Path(__file__).relative_to(Path(__file__).parents[2])),
        'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'harness_sha256': hashlib.sha256(code.encode()).hexdigest(),
        'dotnet_sdk': subprocess.check_output([args.dotnet, '--version'], text=True).strip(),
        'benchmark_id': 'csharp-spring-response-getters-2026.1.1',
        'scope': 'Verbatim response getters with controlled fields; not a constitutive or full-solver oracle',
        'source_sha256': {str(path.relative_to(args.source_root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()},
        'cases': [{**case, 'expected_bits': expected} for case, expected in zip(cases, json.loads(output))],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Wrote {len(cases)} native getter cases to {args.output}')


if __name__ == '__main__':
    main()
