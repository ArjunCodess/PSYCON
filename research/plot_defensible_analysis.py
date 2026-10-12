"""Build publication figures from aggregate nested-group diagnostics."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    root=Path('.runtime/defensible-analysis'); s=json.loads((root/'summary.json').read_text())
    rows=json.loads((root/'nested-predictions.json').read_text())
    common=s['common_original_coverage']
    systems=['original','revised','median']; labels=['Original logistic','Nested selection','Training median']
    colors=['#315a91','#c18b31','#697581']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name,note):
        fig.text(.02,.01,note,fontsize=9,color='#444');fig.tight_layout(rect=(0,.05,1,.97))
        for suffix in ['png','pdf']:fig.savefig(root/(name+'.'+suffix),dpi=180,facecolor='white')
        plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(14,4.5))
    for ax,key,title,multiply in zip(axes,['accuracy','mae','macro_sensitivity'],
                                   ['Exact agreement (%)','Mean absolute error; lower is better','Mean observed-class sensitivity (%)'],[100,1,100]):
        vals=[common[k][key]*multiply for k in systems]
        bars=ax.bar(labels,vals,color=colors);ax.bar_label(bars,fmt='%.1f' if multiply==100 else '%.3f',padding=4)
        ax.tick_params(axis='x',labelrotation=15);ax.set_title(title,fontsize=11)
        ax.set_ylim(0,100 if multiply==100 else .7)
    save(fig,'09-nested-comparison','Identical 402 item observations. Retrospective development; zero independent final-test examples. Revised accuracy improves, sensitivity falls.')
    fig,ax=plt.subplots(figsize=(10,4.5))
    values=np.array([[c['sensitivity']*100 for c in common[k]['by_score'][1:]] for k in systems])
    im=ax.imshow(values,vmin=0,vmax=100,cmap='Blues',aspect='auto')
    ax.set_xticks(range(4),[f"Rating {c['score']}\nn={c['support']}" for c in common['original']['by_score'][1:]])
    ax.set_yticks(range(3),labels);ax.set_title('Exact-score sensitivity: which ratings are detected?')
    for i in range(3):
        for j in range(4):ax.text(j,i,f'{values[i,j]:.1f}%',ha='center',va='center',color='white' if values[i,j]>55 else '#222')
    fig.colorbar(im,ax=ax,label='Sensitivity (%)')
    save(fig,'10-score-sensitivity','One-versus-rest exact-rating recall, not clinical sensitivity. Score 0 has no observations. Pooled targets have different behavioral meanings.')
    fig,axes=plt.subplots(1,3,figsize=(14,4.7))
    for ax,k,label in zip(axes,systems,labels):
        cm=np.array(common[k]['confusion']);den=cm.sum(axis=1,keepdims=True)
        normalized=np.divide(cm,den,out=np.zeros_like(cm,dtype=float),where=den!=0)
        ax.imshow(normalized,vmin=0,vmax=1,cmap='Blues');ax.set_title(label);ax.set_xticks(range(5));ax.set_yticks(range(5));ax.set_xlabel('Predicted score')
        for i in range(5):
            for j in range(5):ax.text(j,i,'N/A' if den[i,0]==0 else str(cm[i,j]),ha='center',va='center',color='white' if normalized[i,j]>.55 else '#222')
    axes[0].set_ylabel('Raw source rating')
    save(fig,'11-normalized-confusion','Row-normalized color; annotations show raw counts on identical 402 labels. Zero-support rows are unavailable, not perfect sensitivity.')
    groups=sorted({r['group'] for r in rows});fig,ax=plt.subplots(figsize=(9,4.8));x=np.arange(len(groups));w=.35
    model=[np.mean([abs(r['rating']-r['prediction']) for r in rows if r['group']==g]) for g in groups]
    baseline=[np.mean([abs(r['rating']-r['baseline']) for r in rows if r['group']==g]) for g in groups]
    ax.bar(x-w/2,model,w,color=colors[1],label='Nested procedure');ax.bar(x+w/2,baseline,w,color=colors[2],label='Training median')
    ax.set_xticks(x,[f'{g}\nn={sum(r["group"]==g for r in rows)}' for g in groups]);ax.set_ylabel('Mean absolute score error');ax.set_ylim(0,max(model+baseline)*1.2);ax.legend();ax.set_title('Performance differs across omitted known groups')
    save(fig,'12-group-errors','All 423 labels, including explicit reference fallbacks. Five known groups; unknown overlap and unreviewed ratings remain.')
    with (root/'class-sensitivity.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['system','score','support','predicted','sensitivity','precision','specificity','tp','fn','fp','tn']);writer.writeheader()
        for system in systems:
            for c in common[system]['by_score']:writer.writerow(dict(system=system,**c))
    print('Four figures and class-sensitivity.csv written')
    alternative=json.loads((root/'sensitivity-summary.json').read_text())['common_original_coverage']
    with (root/'class-sensitivity.csv').open('a',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['system','score','support','predicted','sensitivity','precision','specificity','tp','fn','fp','tn'])
        for c in alternative['by_score']:writer.writerow(dict(system='sensitivity_selection',**c))
    comparisons=[common['original'],common['revised'],alternative,common['median']]
    names=['Original','MAE selection','Sensitivity selection','Median reference']
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,key,title in zip(axes,['accuracy','macro_sensitivity'],['Exact agreement (%)','Mean observed-class sensitivity (%)']):
        bars=ax.bar(names,[m[key]*100 for m in comparisons],color=['#315a91','#c18b31','#9b586c','#697581'])
        ax.bar_label(bars,fmt='%.1f',padding=4);ax.set_ylim(0,100);ax.tick_params(axis='x',labelrotation=20);ax.set_title(title)
    save(fig,'13-objective-tradeoff','Same 402 observations. Sensitivity-oriented post-hoc exploration did not outperform original class-average sensitivity; no independent test.')


if __name__=='__main__':main()
