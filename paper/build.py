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
    revised = json.loads((ROOT / 'docs/report_assets/defensible-source-summary.json').read_text(encoding='utf-8'))
    common = revised['common_original_coverage']
    methods = ['original', 'revised', 'median']
    if any(common[m]['n'] != common['n'] or sum(map(sum,common[m]['confusion'])) != common['n'] for m in methods):
        raise ValueError('Nested comparison denominators do not match')
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), layout='constrained')
    labels = ['Original', 'Nested selection', 'Median reference']
    colors = ['#315a91', '#c18b31', '#697581']
    for ax, key, title in [(axes[0], 'accuracy', 'Exact raw-score agreement (%)'),
                            (axes[1], 'macro_sensitivity', 'Mean observed-class sensitivity (%)')]:
        bars=ax.bar(labels,[common[m][key]*100 for m in methods],color=colors)
        ax.bar_label(bars,fmt='%.1f',padding=4); ax.set_ylim(0,100)
        ax.set_title(title,fontsize=10); ax.tick_params(axis='x',labelrotation=15)
        ax.spines[['top','right']].set_visible(False)
    fig.savefig(folder/'source-nested-comparison.pdf')
    fig.savefig(folder/'source-nested-comparison.png',dpi=180)
    plt.close(fig)
    compact=json.loads((ROOT/'docs/report_assets/compact-source-summary.json').read_text(encoding='utf-8'))
    compared=[common['original'],compact['common'],compact['median_common']]
    if any(m['n']!=402 or sum(map(sum,m['confusion']))!=402 for m in compared):
        raise ValueError('Compact comparison must use the same 402 labels')
    fig,axes=plt.subplots(1,3,figsize=(11,3.6),layout='constrained')
    labels=['Original','Compact procedure','Median reference'];colors=['#315a91','#2c786a','#697581']
    for ax,key,title,mult in zip(axes,['accuracy','mae','macro_sensitivity'],
                                ['Exact agreement (%)','Mean absolute error','Mean class sensitivity (%)'],[100,1,100]):
        bars=ax.bar(labels,[m[key]*mult for m in compared],color=colors)
        ax.bar_label(bars,fmt='%.1f' if mult==100 else '%.3f',padding=4)
        ax.set_ylim(0,100 if mult==100 else .7);ax.tick_params(axis='x',labelrotation=20)
        ax.set_title(title,fontsize=9);ax.spines[['top','right']].set_visible(False)
    fig.savefig(folder/'source-compact-comparison.pdf');fig.savefig(folder/'source-compact-comparison.png',dpi=180)
    plt.close(fig)


def audit_figure():
    """Build the latest comparison from aggregate metrics, without private inputs."""
    source = ROOT / 'docs/report_assets/maximum-defensible-summary.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    names = ['original', 'compact', 'fixed:median', 'fixed:mode', 'nested_challenger',
             'diagnostic:pooled-core-logistic-0.01']
    labels = ['Original', 'Compact', 'Median', 'Mode', 'Nested', 'Fixed diagnostic']
    records = [data['procedures'][n]['common_402'] for n in names]
    if any(r['evaluated'] != 402 or sum(c['support'] for c in r['per_class']) != 402
           or not abs(r['exact_agreement']-r['correct']/402) < 1e-12 for r in records):
        raise ValueError('Latest audit figure must use the fixed 402-rating cohort')
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), layout='constrained')
    bars = axes[0].bar(labels, [r['exact_agreement']*100 for r in records],
                      color=['#315a91', '#2c786a', '#697581', '#697581', '#c18b31', '#999999'])
    axes[0].bar_label(bars, fmt='%.2f', padding=3, fontsize=8)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel('Exact agreement (%)')
    axes[0].tick_params(axis='x', labelrotation=35, labelsize=8)
    axes[0].spines[['top', 'right']].set_visible(False)
    recall = [[r['per_class'][k]['recall']*100 for k in range(1, 5)] for r in records]
    im = axes[1].imshow(recall, vmin=0, vmax=100, cmap='Blues', aspect='auto')
    axes[1].set_yticks(range(len(labels)), labels, fontsize=8)
    axes[1].set_xticks(range(4), ['Score 1', 'Score 2', 'Score 3', 'Score 4'])
    axes[1].set_title('Exact-score recall (%); score 0 unobserved', fontsize=9)
    for i, values in enumerate(recall):
        for j, value in enumerate(values):
            axes[1].text(j, i, f'{value:.1f}', ha='center', va='center', fontsize=8,
                         color='white' if value > 60 else 'black')
    fig.colorbar(im, ax=axes[1], shrink=.75)
    folder = HERE / 'figures'
    fig.savefig(folder / 'maximum-defensible-comparison.pdf')
    fig.savefig(folder / 'maximum-defensible-comparison.png', dpi=180)
    plt.close(fig)


def build():
    figures()
    audit_figure()
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
