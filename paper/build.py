"""Build the BEHA paper and exactly two-page synopsis from committed inputs."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def figures():
    source = ROOT / "docs/report_assets/nemotron-benchmark-summary.json"
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    methods = ["existing", "nvidia", "psycon", "psycon-recovered",
               "nemotron-streaming-guarded", "nemotron-offline"]
    labels = ["Original", "Earlier NVIDIA", "First PSYCON", "Guarded PSYCON",
              "Guarded Nemotron streaming", "Guarded Nemotron offline"]
    counts = [data["totals"][m] for m in methods]
    for method, count in zip(methods, counts):
        actual = sum(r["methods"][method]["ready_profiles"] for r in data["records"])
        if actual != count:
            raise ValueError(f"Benchmark total mismatch for {method}")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(8, 3.5), layout="constrained")
    bars = ax.barh(labels[::-1], counts[::-1], color=["#7a8790", "#7a8790", "#24664e", "#7a8790", "#7a8790", "#7a8790"])
    ax.bar_label(bars, padding=5)
    ax.set_xlim(0, data["marked_slots"])
    ax.set_xlabel("Ready profiles across 85 person-recording slots")
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.grid(True, alpha=.2)
    ax.set_axisbelow(True)
    folder = HERE / "figures"
    folder.mkdir(exist_ok=True)
    fig.savefig(folder / "coverage.pdf", metadata={"Title": "Ready-profile coverage; not psychological accuracy"})
    fig.savefig(folder / "coverage.png", dpi=180)
    plt.close(fig)
    training = json.loads((ROOT / 'docs/report_assets/source-cross-validation-summary.json').read_text(encoding='utf-8'))
    targets = sorted(training['by_target'], key=lambda t: (len(t), int(t[1:]) if len(t)>1 else ord(t)))
    values = training['by_target']
    if sum(values[t]['training']['n'] for t in targets) != training['training']['n']:
        raise ValueError('Training metric denominators do not match target counts')
    if sum(values[t]['retrospective_cv']['n'] for t in targets) != training['retrospective_cv']['n']:
        raise ValueError('CV metric denominators do not match target counts')
    x = list(range(len(targets)))
    fig, ax = plt.subplots(figsize=(9, 3.8), layout='constrained')
    ax.bar([v-.18 for v in x], [values[t]['training']['accuracy']*100 for t in targets], .36, label='Training resubstitution', color='#315a91')
    ax.bar([v+.18 for v in x], [values[t]['retrospective_cv']['accuracy']*100 for t in targets], .36, label='Retrospective grouped CV', color='#c18b31')
    ax.set_xticks(x, targets)
    ax.set_ylim(0, 105)
    ax.set_ylabel('Exact raw source-rating agreement (%)')
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(fontsize=9)
    fig.savefig(folder / 'source-training-cv.pdf')
    fig.savefig(folder / 'source-training-cv.png', dpi=180)
    plt.close(fig)


def build():
    figures()
    compiler = shutil.which("latexmk")
    if not compiler:
        raise RuntimeError("Install a TeX runtime with latexmk, pdflatex and bibtex")
    with tempfile.TemporaryDirectory(prefix="psycon-paper-") as temporary:
        directory = Path(temporary)
        env = dict(os.environ)
        env["TEXINPUTS"] = str(HERE) + os.pathsep + env.get("TEXINPUTS", "")
        env["BIBINPUTS"] = str(HERE) + os.pathsep + env.get("BIBINPUTS", "")
        verified = []
        for stem in ("main", "synopsis"):
            command = [compiler, "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                       "-file-line-error", f"-outdir={directory}", f"{stem}.tex"]
            result = subprocess.run(command, cwd=HERE, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (ROOT / ".runtime/docs-review").mkdir(parents=True, exist_ok=True)
            (ROOT / f".runtime/docs-review/{stem}-build.log").write_text(result.stdout, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(f"{stem} compilation failed; see .runtime/docs-review/{stem}-build.log")
            log = (directory / f"{stem}.log").read_text(encoding="utf-8", errors="replace")
            rejected = ["Overfull", "undefined references", "undefined citations", "Citation `", "Reference `"]
            if any(token in log for token in rejected):
                raise RuntimeError(f"{stem} has layout/citation warnings; see build log")
            pdf = directory / f"{stem}.pdf"
            with pymupdf.open(pdf) as document:
                if stem == "synopsis" and len(document) != 2:
                    raise RuntimeError(f"Synopsis must be two pages, got {len(document)}")
                if any(not page.get_text().strip() for page in document):
                    raise RuntimeError(f"{stem} has an empty page")
                print(f"{stem}: {len(document)} pages")
            verified.append((pdf, HERE / f"{stem}.pdf"))
        for source, destination in verified:
            shutil.copyfile(source, destination)


if __name__ == "__main__":
    build()
