"""Figures for the disclosed compact-source procedure, never winner selection."""
import json,csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
 p=Path('.runtime/model-hardening');s=json.loads((p/'summary.json').read_text());r=json.loads((p/'predictions.json').read_text())
 old=json.loads(Path('docs/report_assets/defensible-source-summary.json').read_text())['common_original_coverage']
 sensitivity=json.loads(Path('docs/report_assets/sensitivity-source-summary.json').read_text())['common_original_coverage']
 systems=[old['original'],old['revised'],sensitivity,s['common'],s['median_common']]
 labels=['Original','MAE repair','Sensitivity repair','Compact procedure','Median reference'];colors=['#315a91','#ae7f2b','#9b586c','#2c786a','#697581']
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
 def save(fig,name,note):
  fig.text(.02,.01,note,fontsize=8,color='#444');fig.tight_layout(rect=(0,.06,1,.96))
  for ext in ('png','pdf'):fig.savefig(p/(name+'.'+ext),dpi=180,facecolor='white')
  plt.close(fig)
 fig,axes=plt.subplots(1,3,figsize=(15,4.9))
 for ax,key,title,mult in zip(axes,['accuracy','mae','macro_sensitivity'],['Exact agreement (%)','Mean absolute error','Mean class sensitivity (%)'],[100,1,100]):
  bars=ax.bar(labels,[v[key]*mult for v in systems],color=colors);ax.bar_label(bars,fmt='%.1f' if mult==100 else '%.3f',padding=4)
  ax.tick_params(axis='x',labelrotation=28);ax.set_ylim(0,100 if mult==100 else .7);ax.set_title(title)
 save(fig,'14-final-procedure-comparison','Same 402 labels; retrospective development, zero independent final-test examples. References remain better in exact agreement and error.')
 fig,ax=plt.subplots(figsize=(10,5.3));a=np.array([[c['sensitivity']*100 for c in v['by_score'][1:]] for v in systems])
 im=ax.imshow(a,vmin=0,vmax=100,cmap='Blues',aspect='auto');ax.set_yticks(range(5),labels)
 ax.set_xticks(range(4),[f"Score {c['score']}\nn={c['support']}" for c in s['common']['by_score'][1:]])
 for i in range(5):
  for j in range(4):ax.text(j,i,f'{a[i,j]:.1f}%',ha='center',va='center',color='white' if a[i,j]>55 else '#222')
 ax.set_title('Exact-score sensitivity exposes minority-score failure');fig.colorbar(im,ax=ax,label='Sensitivity (%)')
 save(fig,'15-final-sensitivity','Exact-rating recall, not clinical sensitivity. Score 0 is unobserved. Targets do not form a single validated psychological construct.')
 fig,axes=plt.subplots(1,2,figsize=(10,5))
 for ax,v,label in zip(axes,[s['common'],s['median_common']],['Compact procedure','Median reference']):
  cm=np.asarray(v['confusion']);den=cm.sum(axis=1,keepdims=True);z=np.divide(cm,den,out=np.zeros_like(cm,dtype=float),where=den!=0)
  ax.imshow(z,vmin=0,vmax=1,cmap='Blues');ax.set_title(label);ax.set_xticks(range(5));ax.set_yticks(range(5));ax.set_xlabel('Predicted score');ax.set_ylabel('Source score')
  for i in range(5):
   for j in range(5):ax.text(j,i,'N/A' if den[i,0]==0 else str(cm[i,j]),ha='center',va='center',color='white' if z[i,j]>.55 else '#222')
 save(fig,'16-final-confusion','Row-normalized colors; raw counts shown. Same 402 observations; N/A denotes no source observations, not perfect performance.')
 targets=sorted(s['per_target']);fig,ax=plt.subplots(figsize=(12,4.8));x=np.arange(len(targets));w=.38
 reference={t:np.mean([abs(a['rating']-a['baseline']) for a in r if a['target']==t]) for t in targets}
 ax.bar(x-w/2,[s['per_target'][t]['mae'] for t in targets],w,label='Compact procedure',color=colors[3]);ax.bar(x+w/2,[reference[t] for t in targets],w,label='Median reference',color=colors[4])
 ax.set_xticks(x,[f"{t}\nn={s['per_target'][t]['n']}" for t in targets]);ax.set_ylabel('Mean absolute error');ax.set_title('All targets, including explicit reference fallbacks');ax.legend()
 save(fig,'17-final-target-errors','All 423 labels. Reference constants are not individualized predictions. Different targets have different meanings; small samples limit inference.')
 candidates=list(s['fixed_candidate_diagnostics']);fig,axes=plt.subplots(1,2,figsize=(14,6));y=np.arange(len(candidates))
 for ax,key,title in zip(axes,['mae','macro_sensitivity'],['Ordinal error; lower is better','Mean observed-class sensitivity (%)']):
  vals=[s['fixed_candidate_diagnostics'][c][key]*(100 if key!='mae' else 1) for c in candidates]
  bars=ax.barh(y,vals,color=colors[3]);ax.bar_label(bars,fmt='%.3f' if key=='mae' else '%.1f',padding=4);ax.set_yticks(y,candidates);ax.invert_yaxis();ax.set_title(title)
  ax.set_xlim(0,.85 if key=='mae' else 100)
 save(fig,'18-fixed-candidate-audit','All 423 labels. Diagnostics are not independent tests and must not select an outer-result winner. The nested procedure is reported separately.')
 fig,axes=plt.subplots(1,2,figsize=(10,4.7))
 for ax,key,title,mult in zip(axes,['accuracy','mae'],['Exact agreement (%)','Mean absolute score error'],[100,1]):
  bars=ax.bar(['Final fit replay\nn=423','Nested group CV\nn=423','Independent test\nn=0'],
      [s['final_training_replay'][key]*mult,s['nested'][key]*mult,0],color=['#315a91','#2c786a','#ddd'])
  for bar in bars[:2]:ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+(.015 if mult==1 else 2),f'{bar.get_height():.3f}' if mult==1 else f'{bar.get_height():.1f}',ha='center')
  ax.text(2,.04 if mult==1 else 4,'Unavailable',ha='center');ax.set_ylim(0,.7 if mult==1 else 100);ax.set_title(title)
 save(fig,'19-training-evaluation-audit','Final fitting uses all examples. Nested CV evaluates the selection procedure. Independent-test performance is unavailable, not zero error or zero agreement.')
 with (p/'class-metrics.csv').open('w',newline='',encoding='utf-8') as f:
  writer=csv.DictWriter(f,fieldnames=['system','score','support','predicted','sensitivity','precision','specificity','tp','fn','fp','tn']);writer.writeheader()
  for label,v in zip(labels,systems):
   for c in v['by_score']:writer.writerow(dict(system=label,**c))
 print('Six final figures and complete same-label class metrics written')


if __name__=='__main__':main()
