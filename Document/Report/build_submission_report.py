from pathlib import Path
import json, math, html, collections
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / 'Lab01_23127005_23127028_23127183_23127536_23127042'
SUMMARY = SUB / 'logs/tests/run-4udyr5el/summary.json'
results = json.loads(SUMMARY.read_text(encoding='utf-8'))
assert results['tests_run'] == 150 and results['successful']
assert all(t['status'] == 'passed' for t in results['tests'])
pdfmetrics.registerFont(TTFont('Arial', 'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold', 'C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial', boldItalic='Arial-Bold')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Body', fontName='Arial', fontSize=10, leading=14, spaceAfter=8))
styles.add(ParagraphStyle(name='TitleX', fontName='Arial-Bold', fontSize=23, leading=28, textColor=colors.HexColor('#17354b'), spaceAfter=16))
styles.add(ParagraphStyle(name='Head', fontName='Arial-Bold', fontSize=14, leading=19, textColor=colors.HexColor('#17354b'), spaceBefore=10, spaceAfter=10))
styles.add(ParagraphStyle(name='SmallX', fontName='Arial', fontSize=8.2, leading=11, spaceAfter=5, splitLongWords=True))
styles.add(ParagraphStyle(name='TinyX', fontName='Arial', fontSize=7.5, leading=10, spaceAfter=3, splitLongWords=True))
story=[]
def p(text, style='Body'):
    return Paragraph(text, styles[style])
def add(text, style='Body'):
    story.append(p(text,style))
def head(text): add(text,'Head')
def page(title):
    if story: story.append(PageBreak())
    add(title,'TitleX')
def table(rows, widths, small=True):
    data=[[p(str(v), 'SmallX' if small else 'Body') for v in row] for row in rows]
    t=Table(data,colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5edf3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#17354b')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#ccd5dc')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(t)

page('Lab 01 | Blockchain Layer 1')
add('Blockchain course, 2026 - Knowledge Engineering Department<br/>Submission report | Verified 06 November 2026', 'SmallX')
head('Team members')
table([['Name','Student ID'],['Nguyễn Anh Kiệt','23127005'],['Phan Thanh Bình','23127028'],['Phạm Vũ Ngọc Duy','23127183'],['Nguyễn Tấn Phước','23127536'],['Nguyễn Đặng Minh Duy','23127042']],[340,155])
head('1. Purpose and design choices')
add('The simulator models a minimal Layer 1 blockchain: validators exchange signed messages and agree on an ordered ledger and key-value application state. It uses a Tendermint-style PROPOSE / PREVOTE / PRECOMMIT protocol with locking, certificates and rotating proposers. Safety is checked separately from completion and convergence.')
add('The standard configuration requires n = 3f + 1 and n ≥ 8, with at most f Byzantine validators. Defaults are n=10, f=3, quorum Q=7, seed=42 and five heights. Partial synchrony is represented by GST and a post-GST delivery bound delta. Deterministic event scheduling enables reproducible fault experiments.')
head('2. Submission structure')
table([['Item','Contents / purpose'],['src/','Nine runtime modules; module entry point src.main.'],['tests/','Unit, integration, E2E, regression, independent oracle and mutation tests.'],['logs/','Fresh simulator logs, acceptance console and per-test event logs with summary.json.'],['config/','default.json and fixed identities.json fixture.'],['README.md / requirements.txt','Setup, simulator and test commands; pinned cryptography dependency.'],['REPORT.pdf','This report. No source code is embedded.']],[145,350])
add('The five IDs in the folder name follow the member order above. The runnable submission has no dependency on the repository-level Document/ or temp/ folders.','SmallX')

page('3. System design and flow')
head('Module interactions')
d=Drawing(495,200)
boxes=[(0,143,145,44,'main / configuration','bootstrap + scenario'),(175,143,145,44,'Node / consensus','gossip + lock + sync'),(350,143,145,44,'Net / simulator','queue + transport'),(0,42,145,44,'identities / common','keys + signed models'),(175,42,145,44,'execution / State','atomic transaction batch'),(350,42,145,44,'validation / logs','safety + completion')]
for x,y,w,h,a,b in boxes:
    d.add(Rect(x,y,w,h,rx=5,fillColor=colors.HexColor('#edf3f7'),strokeColor=colors.HexColor('#59778e')))
    d.add(String(x+w/2,y+27,a,fontName='Arial-Bold',fontSize=9,textAnchor='middle'))
    d.add(String(x+w/2,y+12,b,fontName='Arial',fontSize=8,textAnchor='middle'))
def arrow(x1,y1,x2,y2):
    d.add(Line(x1,y1,x2,y2,strokeColor=colors.HexColor('#17354b')))
    if x1==x2: pts=[x2,y2,x2-3,y2+7,x2+3,y2+7]
    else: pts=[x2,y2,x2-7,y2-3,x2-7,y2+3]
    d.add(Polygon(pts,fillColor=colors.HexColor('#17354b'),strokeColor=None))
arrow(145,165,175,165);arrow(320,165,350,165);arrow(72,143,72,86);arrow(247,143,247,86);arrow(422,143,422,86)
story.append(d)
add('<b>Bootstrap:</b> main loads JSON, validates BFT parameters and accounts, creates the network, loads fixed validator/account keys, instantiates honest or configured Byzantine nodes, and admits initial transactions through the transaction handler. Byzantine subclasses operate through network messages; they do not directly mutate another node’s ledger.')
add('<b>Transaction path:</b> on_tx validates shape, account, domain signature, namespace and nonce freshness before mempool admission. A seen-hash set suppresses re-gossip of accepted duplicates. A proposer sorts candidates by sender/nonce and applies them on temporary state to choose a bounded valid batch.')
head('Proposal, consensus and catch-up')
add('<b>Normal proposal:</b> proposer → HEADER → receiver checks identity, signature and window → REQUEST_BODY → BODY → check transaction commitment, execute the ordered batch and compare state hash → PREVOTE. Unsupported bodies are not accepted without an approved header. Missing-body requests are retried and buffers are bounded.')
add('<b>Agreement:</b> Q matching, distinct PREVOTEs create a lock and justify PRECOMMIT. Q authenticated PRECOMMITs for one non-NIL block create a commit certificate. A node finalizes only after block validation; it updates ledger/state, records the certificate and advances height. Proposer selection is (height + round) modulo n.')
add('<b>Catch-up:</b> a lagging node asks SYNC_REQ, receives SYNC_HEADERS with finality certificates, requests the approved bodies, verifies certificate/parent/execution commitments and finalizes missing blocks in order. The full SYNC_RESP handler also validates complete block/certificate envelopes used by compatibility and focused tests.')

page('4. Implementation notes')
head('Consensus guards')
table([['Guard','Realization'],['1. One PREVOTE per slot','The signed map reserves (height, round, PREVOTE); a second conflicting signature cannot be emitted.'],['2. One PRECOMMIT per slot','PRECOMMIT has its own reserved slot; late information cannot cause double signing.'],['3. Validate before voting','Check proposer, signed header, parent, transaction root, transaction signatures/ownership/nonces and computed state hash. Invalid data never authorizes a block vote.'],['4. Lock on a prevote quorum','Require Q=2f+1 distinct authenticated PREVOTEs for the same non-NIL block. A late quorum can update the lock without signing twice or moving a lock backward.'],['5. Safe lock changes','A different block requires a valid proof of lock at a newer round. POLKA carries original PREVOTEs; a claimed pol_round alone is insufficient.'],['6. Vote context','Phase, height/round, chain-specific VOTE domain, validator membership and signature bind a vote to its intended slot.'],['7. One vote per signer','The vote map is keyed by signer per slot. Duplicates cannot increase quorum; conflicting votes produce EQUIVOCATION evidence.']],[132,363])
head('Gossip, scheduling and execution')
add('Valid transactions are broadcast once upon first admission. Proposal transfer uses header-first retrieval, while proof/certificate messages provide authenticated evidence for lock changes and finality. Logical unicast/broadcast follows configured topology and routes through actual links; routed traffic still uses the simulator transport pipeline.')
add('Net uses a heap ordered by virtual time and an increasing sequence number, with an isolated seeded RNG. Deliveries deep-copy payloads to prevent shared mutable certificate state. Before GST it can delay, drop, duplicate and reorder traffic. Outbound capacity is shared across a node; peer admission may wait before SEND. After GST routed hops share one end-to-end delta budget.')
add('Timeouts grow as base_timeout + round × timeout_inc. At least f+1 distinct validators at higher rounds can justify skipping ahead; f Byzantine validators alone cannot force that skip. Ed25519 signatures separate TX, HEADER and VOTE domains by chain ID. SHA-256 commitments use canonical encoding. The transaction commitment is a flat hash of the ordered list, not a Merkle tree.')
add('Execution validates each transaction and runs a batch on copied state; failure discards the batch. State hashing includes both application data and nonces in stable order. Block identity commits to height, parent, state hash and transaction root, remaining stable across reproposals.','SmallX')

page('5. Bugs, corrections and limits')
add('These issues are documented by existing regression tests and implementation notes. The packaging pass preserved the runtime and test assertions; it did not reimplement consensus.')
table([['Issue / observed failure mode','Correction and regression evidence'],['Missing winning body after equivocation','A node receiving a losing proposal first could lack the block later certified by honest validators. Retain relevant alternatives and retrieve approved missing bodies; E2E proposer-equivocation seeds check both safety and full honest progress.'],['Trusting claimed proof metadata','pol_round without authenticated PREVOTEs is not evidence. POLKA verification checks phase, signatures, height/round/hash and distinct quorum signers before allowing reproposal or unlock.'],['Header buffer starvation','Speculative/future headers could crowd out useful proposals. Bounded admission protects proof/lock/finality data and favors current or certified headers; regression cases cover stale cleanup and future-round pressure.'],['Malformed or cached-block sync','Malformed envelopes could raise exceptions; an already cached valid block could miss finality processing. Validate types/fields before arithmetic and finalize a fully checked cached block against its certificate exactly once.'],['Routed capacity and delta accounting','Per-hop delay budgeting or later admission could violate end-to-end timing or reserved capacity. Reserve the full route and account for future reservations; regression checks actual SEND windows and delivery bounds.'],['Identical incomplete simulations','Two identical logs do not prove progress. Require all honest nodes to reach the requested height and converge before reporting deterministic success. Negative controls include incomplete runs and a mismatch on V9.']],[172,323])
head('Trust and scope')
add('The identity file is a private fixture for the simulator’s trusted setup, fixed independently of network randomness. Reproducibility requires retaining it. It is not a production key-management system. RPC services, crash-recovery WAL, a Merkle Patricia Trie and real network deployment are outside this minimal simulator.')
add('The n=9, f=3, Q=6 coalition experiment intentionally violates the standard n=3f+1 assumption. It is expected to expose a safety fork; n=10, Q=7 is a control. A passing experiment means its assertion observed the intended boundary, not that the unsafe configuration became safe.')

page('6. Testing and observed results')
add('Verified after relocation on Windows using Python 3.12.14 and cryptography 50.0.2. The logged single entry point ran <b>150 tests in 35.265 seconds: 150 passed, 0 failures, 0 errors, 0 skips</b>. Test-method counts do not separately count subtest variants. The evidence index is logs/tests/run-4udyr5el/summary.json; the console transcript is logs/acceptance-console.txt.')
table([['Case / input','Expected behavior and observed outcome'],['T1 - normal network','No fault schedule; identical complete honest ledgers and state. PASS: round-zero finalization, expected account data and nonces checked.'],['T2 - duplicates / reorder','At most one counted vote per signer/slot; no conflicting honest finalization. PASS: injected fault events and safety checked.'],['T3 - invalid signatures','Reject corrupt or wrong-domain TX/header/vote/certificate with reason; continue honest progress. PASS at component and E2E levels.'],['T4 - transaction replay','Send a valid TX through the network, replay before and after commit. PASS: dissemination occurs, application/nonce advances once and replay cannot reapply it.'],['T5 - pre-GST faults','Delay/drop schedules and multiple seeds must retain safety; scenarios requiring recovery also check progress. PASS: fault injection and finality checks hold.'],['T6 - silent proposer','Timeout and move to a later round, completing the honest chain. PASS for one silent and three silent validators.'],['T7 - equivocation','Conflicting proposer/voter messages produce evidence without honest forks. PASS: attacks occur and honest progress/certificates remain valid.'],['T8 - deterministic replay','Two runs with the same config/seed/identity have byte-identical logs and all-honest snapshots. PASS, including independent-process checks and negative controls.']],[145,350])
head('Fresh default simulator run')
add('The default CLI was invoked with --twice after relocation. Both runs completed five blocks, log bytes matched, and all honest nodes agreed on ledger/state. Alice/msg, Bob/msg and Carol/msg each equal v5. Final state hash:','Body')
add('0b837be96db72e1f18691d048ad593734a90169c56e518f13441334887b3d307','SmallX')
add('Evidence: logs/simulator-console.txt, logs/run.log and logs/run.second.log. Negative controls, deliberately injected invalid messages and out-of-model forks are expected anomalies. No unexpected failure was observed in this verification. Passing these deterministic examples is regression evidence, not a proof for all Byzantine strategies.','SmallX')

page('7. Additional coverage and references')
table([['Test family','Expected outcome; observed result'],['Execution and signatures','Reject invalid ownership, nonce, signature or domain; preserve atomic state. Valid controls succeed. All passed.'],['Transport and synchronization','Honor topology, drops, throttling and timing; reject malformed sync and invalid certificates; valid catch-up completes. All passed.'],['Safety helpers and logging','Detect conflicting or stalled honest ledgers; preserve original assertion/fixture failures, CLI exit codes and log indexes. All passed.'],['Consensus / network / CLI regressions','Protect lock/proof, missing-body, buffer, payload isolation, route reservations, configuration and incomplete-run fixes. All passed.'],['Independent oracle','Recompute encoding, commitments, transaction execution and signatures independently of production helpers; check each honest ledger, state and certificate. Scenario checks passed.'],['Seven mutation gates','Disable admission/gossip or Byzantine factory; corrupt signature/domain acceptance, nonce guard, duplicate counting or state-root checks. Each designated behavioral assertion must fail for its mutant. All seven gates passed.'],['Quorum boundary','Observe the expected out-of-model fork and safe controls; distinguish stalled liveness from conflicting finalization. All corresponding assertions passed.']],[146,349])
add('The following three pages enumerate every executed test method with its observed status. Test IDs map directly to per-test log files through summary.json. Method names describe individual triggers; the matrices above state the acceptance criteria shared by those cases. The complete test assertions remain in tests/, outside the report.','SmallX')
head('References and submission materials')
refs=[
'Course handout: Blockchain course, Lab01, Knowledge Engineering Department, 2026, especially §§3, 5-10; course Lab01-presentation slides. Repository originals: Document/Lab01.pdf and Document/Lab01-presentation.pdf (outside the runnable package).',
'Buchman, Kwon, Milosevic. The latest gossip on BFT consensus (2018). https://arxiv.org/abs/1807.04938',
'Lamport, Shostak, Pease. The Byzantine Generals Problem (1982). https://doi.org/10.1145/357172.357176',
'Dwork, Lynch, Stockmeyer. Consensus in the Presence of Partial Synchrony (1988). https://doi.org/10.1145/42282.42283',
'Josefsson, Liusvaara. RFC 8032: Edwards-Curve Digital Signature Algorithm (EdDSA). https://www.rfc-editor.org/rfc/rfc8032',
'NIST. FIPS PUB 180-4: Secure Hash Standard. https://doi.org/10.6028/NIST.FIPS.180-4',
'Python unittest documentation: https://docs.python.org/3/library/unittest.html ; PyCA Ed25519 API: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/',
'Internal implementation/review notes: Document/IMPLEMENTATION.md, Document/reviews/2026-11-06-cleanup-audit.md; runnable test guide: tests/README.md. This report uses no book excerpts or source-code listings.'
]
for i,r in enumerate(refs,1): add(f'[{i}] '+html.escape(r),'SmallX')

for chunk in range(3):
    page(f'Appendix | Test inventory {chunk+1}/3')
    add('Every entry below was observed PASS in the relocated submission. IDs omit only the common leading “tests.” prefix. See summary.json for the exact filename of each event log.','SmallX')
    for i,t in enumerate(results['tests'][chunk*50:(chunk+1)*50],chunk*50+1):
        name=t['test'].removeprefix('tests.')
        # Allow wrapping at name separators without changing visible identifiers.
        name=html.escape(name).replace('.', '.<wbr/>').replace('_','_<wbr/>')
        add(f'<b>{i:03d} PASS</b>  {name}','TinyX')

def footer(c,doc):
    c.saveState(); c.setStrokeColor(colors.HexColor('#ccd5dc'));c.line(50,43,545,43)
    c.setFont('Arial',8);c.setFillColor(colors.HexColor('#59778e'))
    c.drawString(50,30,'LAB 01  |  TEAM 23127005 / 23127028 / 23127183 / 23127536 / 23127042')
    c.drawRightString(545,30,str(doc.page));c.restoreState()
out=SUB/'REPORT.pdf'
doc=SimpleDocTemplate(str(out),pagesize=(595.28,841.89),rightMargin=50,leftMargin=50,topMargin=42,bottomMargin=55,title='Lab 01 - Blockchain Layer 1 Simulator',author='Lab 01 Team')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
r=PdfReader(str(out)); print('REPORT pages:',len(r.pages));assert len(r.pages)<=10
assert all((pg.extract_text() or '').strip() for pg in r.pages)
(ROOT/'temp/report-build/extracted.txt').write_text('\n\n'.join(pg.extract_text() for pg in r.pages),encoding='utf-8')
print(out)
