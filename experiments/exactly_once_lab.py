#!/usr/bin/env python3
"""Local SQLite experiment; all measurements produced by running this file."""
import argparse, concurrent.futures, csv, hashlib, json, os, random, sqlite3, subprocess, sys, tempfile, time, statistics
from pathlib import Path


def connect(db):
    c=sqlite3.connect(str(db),timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=FULL')
    return c

def initialize(db):
    c=connect(db)
    c.executescript('''CREATE TABLE dedupe (event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
CREATE TABLE effects (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL, amount INT NOT NULL);
''')
    c.commit(); c.close()

def fingerprint(payload):
    return hashlib.sha256(payload.encode()).hexdigest()

def handle(db, event_id, payload, robust):
    start=time.perf_counter_ns()
    c=connect(db)
    try:
        c.execute('BEGIN IMMEDIATE')
        if robust:
            cur=c.execute('INSERT OR IGNORE INTO dedupe(event_id, fingerprint) VALUES (?,?)',(event_id,fingerprint(payload)))
            if cur.rowcount==1:
                c.execute('INSERT INTO effects(event_id, amount) VALUES (?,?)',(event_id,1))
            else:
                old=c.execute('SELECT fingerprint FROM dedupe WHERE event_id=?',(event_id,)).fetchone()[0]
                if old!=fingerprint(payload): raise ValueError('Same id with different payload')
        else:
            c.execute('INSERT INTO effects(event_id,amount) VALUES (?,?)',(event_id,1))
        c.commit()
    except: c.rollback(); raise
    finally: c.close()
    return (time.perf_counter_ns()-start)/1e6

def quantile(x,p):
    a=sorted(x); pos=(len(a)-1)*p/100; lo=int(pos); hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(pos-lo)

def run_batch(db, seed, unique, copies, workers, robust):
    initialize(db)
    ids=[f'evt-{i:04d}' for i in range(unique) for _ in range(copies)]
    random.Random(seed).shuffle(ids)
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        durations=list(pool.map(lambda i: handle(db,i,'immutable-payload',robust),ids))
    elapsed=time.perf_counter()-start
    c=connect(db)
    total=c.execute('SELECT count(*) FROM effects').fetchone()[0]
    distinct=c.execute('SELECT count(DISTINCT event_id) FROM effects').fetchone()[0]
    dups=c.execute('SELECT count(*) FROM dedupe').fetchone()[0]
    c.close()
    return {'mode':'idempotent' if robust else 'naive','seed':seed,'unique_events':unique,'deliveries':len(ids), 'workers':workers,'effects':total,'distinct_effects':distinct,'dedupe_rows':dups,'duplicate_effects':total-distinct,'elapsed_s':round(elapsed,4),'delivery_throughput_s':round(len(ids)/elapsed,1),'p50_handler_ms':round(quantile(durations,50),4),'p95_handler_ms':round(quantile(durations,95),4)}

def crash_worker(db, when):
    c=connect(db)
    c.execute('BEGIN IMMEDIATE')
    c.execute('INSERT OR IGNORE INTO dedupe(event_id,fingerprint) VALUES (?,?)',('crash-event',fingerprint('immutable-payload')))
    c.execute('INSERT INTO effects(event_id,amount) VALUES (?,?)',('crash-event',1))
    if when=='before': os._exit(71)
    c.commit(); os._exit(72)

def crash_probe(folder):
    result={}
    for when in ['before','after']:
        db=folder/f'crash_{when}.sqlite'
        initialize(db)
        proc=subprocess.run([sys.executable,__file__,'--worker-crash',str(db),when],capture_output=True)
        c=connect(db); pre=c.execute('SELECT count(*) FROM effects').fetchone()[0]; c.close()
        handle(db,'crash-event','immutable-payload',True)
        handle(db,'crash-event','immutable-payload',True)
        c=connect(db); after=c.execute('SELECT count(*) FROM effects').fetchone()[0]; consistency=c.execute('PRAGMA integrity_check').fetchone()[0]; c.close()
        result[when]={'exit_code':proc.returncode,'effects_after_crash':pre,'effects_after_redelivery_twice':after,'integrity_check':consistency,'expected_crash_effects':0 if when=='before' else 1}
    return result

def run(out,unique,copies,workers):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for seed in [17,42,91]:
        for robust in [False,True]:
            db=out/f'batch_{seed}_{int(robust)}.sqlite'
            if db.exists(): db.unlink()
            r=run_batch(db,seed,unique,copies,workers,robust)
            assert r['distinct_effects']==unique
            assert r['effects']==(unique if robust else unique*copies)
            rows.append(r)
    with tempfile.TemporaryDirectory() as t:
        crash=crash_probe(Path(t))
    assert crash['before']['effects_after_crash']==0
    assert crash['after']['effects_after_crash']==1
    assert crash['before']['effects_after_redelivery_twice']==crash['after']['effects_after_redelivery_twice']==1
    # payload conflict checks before committing any second side effect
    db=out/'payload_conflict.sqlite'; initialize(db)
    handle(db,'stable-id','original',True)
    rejected=False
    try: handle(db,'stable-id','altered',True)
    except ValueError: rejected=True
    c=connect(db); effects=c.execute('SELECT count(*) FROM effects').fetchone()[0]; c.close()
    assert rejected and effects==1
    summary={'study':'local sqlite idempotent effects under concurrent duplicate deliveries','python':sys.version.split()[0],'note':'exactly-once effect only inside one SQLite transaction; not transport exactly-once and not external APIs','rows':rows,'crash_probes':crash,'payload_conflict':{'rejected':rejected,'effects':effects},'all_assertions_passed':True}
    (out/'exactly_once_results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    with (out/'exactly_once_results.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,rows[0].keys());writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='results');p.add_argument('--unique',type=int,default=200);p.add_argument('--copies',type=int,default=4);p.add_argument('--workers',type=int,default=8);p.add_argument('--worker-crash',nargs=2)
    a=p.parse_args()
    if a.worker_crash: crash_worker(Path(a.worker_crash[0]),a.worker_crash[1])
    else: run(a.out,a.unique,a.copies,a.workers)
