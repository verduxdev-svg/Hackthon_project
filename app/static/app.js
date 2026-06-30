/* ══════════════════════════════════════════════════════════════
   AI Recruiter — Frontend Logic (Dark Theme)
   All API calls preserved · New UI class names aligned
══════════════════════════════════════════════════════════════ */

'use strict';

// ── State ──
let rawJdText = '';
let uploadedCandidates = [];
let rankedResults = [];

// ── DOM refs ──
const jdRawText       = document.getElementById('jd-raw-text');
const charCount       = document.getElementById('char-count');
const jdDropZone      = document.getElementById('jd-drop-zone');
const jdFileInput     = document.getElementById('jd-file-input');
const jdFileStatus    = document.getElementById('jd-file-status');

const candidateDropZone     = document.getElementById('candidate-drop-zone');
const candidateFileInput    = document.getElementById('candidate-file-input');
const candidatesPreviewList = document.getElementById('candidates-preview-list');
const candidateCountBadge   = document.getElementById('candidate-count-badge');
const clearCandidatesBtn    = document.getElementById('clear-candidates-btn');

const shortlistSizeInput = document.getElementById('shortlist-size');
const runBtn             = document.getElementById('run-ranking-btn');
const downloadBtn        = document.getElementById('download-csv-btn');
const errorBanner        = document.getElementById('error-banner');
const errorText          = document.getElementById('error-text');

const sectionResults  = document.getElementById('section-results');
const loadingState    = document.getElementById('loading-state');
const loadingTextEl   = document.getElementById('loading-text');
const rankingResults  = document.getElementById('ranking-results');
const resultsMeta     = document.getElementById('results-meta');
const extractionPanel = document.getElementById('extraction-preview');
const navResultsLink  = document.getElementById('nav-results-link');
const mobileMenuBtn   = document.getElementById('mobile-menu-btn');
const mobileDrawer    = document.getElementById('mobile-drawer');

// ── Utility: close mobile menu ──
function closeMobileMenu() {
    mobileDrawer.classList.add('hidden');
}

// ── Mobile menu toggle ──
if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', () => {
        mobileDrawer.classList.toggle('hidden');
    });
}

// ── Active nav highlighting on scroll ──
(function setupScrollSpy() {
    const links  = document.querySelectorAll('.nav-link');
    const anchors = ['section-jd','section-candidates','section-run','section-results'];
    const io = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (e.isIntersecting) {
                const id = e.target.id;
                links.forEach(l => {
                    l.classList.toggle('active', l.getAttribute('href') === `#${id}`);
                });
            }
        });
    }, { threshold: 0.45 });
    anchors.forEach(id => {
        const el = document.getElementById(id);
        if (el) io.observe(el);
    });
})();

// ── Health Check ──
(async function checkHealth() {
    const badge = document.getElementById('health-badge');
    const label = badge.querySelector('.hp-label');
    try {
        const res = await fetch('/api/health');
        if (!res.ok) throw new Error();
        const data = await res.json();
        badge.classList.add('online');
        label.textContent = data.status === 'healthy' ? 'System Online' : 'Degraded';
    } catch {
        badge.classList.add('offline');
        label.textContent = 'Offline';
    }
})();

// ── Tab Switcher ──
document.querySelectorAll('.tsw-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tsw-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.tab).classList.add('active');
        checkStep1Complete();
    });
});

// ── Character Counter ──
if (jdRawText) {
    jdRawText.addEventListener('input', () => {
        const len = jdRawText.value.length;
        charCount.textContent = `${len.toLocaleString()} character${len !== 1 ? 's' : ''}`;
        charCount.classList.toggle('enough', len >= 50);
        checkStep1Complete();
    });
}

function checkStep1Complete() {
    const textActive = document.getElementById('tab-text')?.classList.contains('active');
    const ok = textActive ? jdRawText.value.trim().length >= 50 : rawJdText.trim().length >= 50;
    return ok;
}

// ── Drop Zone Utility ──
function setupDropZone(zone, input, onFiles) {
    if (!zone) return;
    zone.addEventListener('click', e => {
        if (e.target.tagName !== 'BUTTON') input.click();
    });
    input.addEventListener('change', () => {
        if (input.files?.length) onFiles(input.files);
    });
    ['dragenter','dragover','dragleave','drop'].forEach(ev =>
        zone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); })
    );
    ['dragenter','dragover'].forEach(ev =>
        zone.addEventListener(ev, () => zone.classList.add('dragover'))
    );
    ['dragleave','drop'].forEach(ev =>
        zone.addEventListener(ev, () => zone.classList.remove('dragover'))
    );
    zone.addEventListener('drop', e => {
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
    });
}

// ── JD Drop Zone Setup ──
setupDropZone(jdDropZone, jdFileInput, files => processJdFile(files[0]));

async function processJdFile(file) {
    setStatus(jdFileStatus, 'loading', `<i class="fa-solid fa-circle-notch fa-spin"></i> Processing ${file.name}…`);

    if (file.name.endsWith('.json')) {
        const reader = new FileReader();
        reader.onload = e => {
            try {
                const data = JSON.parse(e.target.result);
                rawJdText = data.raw_jd_text || JSON.stringify(data);
                setStatus(jdFileStatus, 'success', `<i class="fa-solid fa-circle-check"></i> ${file.name} loaded`);
            } catch {
                setStatus(jdFileStatus, 'error', `<i class="fa-solid fa-triangle-exclamation"></i> Invalid JSON format`);
            }
        };
        reader.readAsText(file);
        return;
    }

    // .docx / .txt → server extraction
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch('/api/extract-jd/file', { method: 'POST', body: fd });
        if (!res.ok) throw new Error();
        const result = await res.json();

        // Set raw text from server-extracted result
        rawJdText = result.extracted_raw_text || '';

        setStatus(jdFileStatus, 'success', `<i class="fa-solid fa-circle-check"></i> ${file.name} — intelligence extracted`);
        showExtractionPanel(result);
    } catch {
        setStatus(jdFileStatus, 'error', `<i class="fa-solid fa-triangle-exclamation"></i> Failed to parse file`);
    }
}

// ── Candidate Drop Zone Setup ──
setupDropZone(candidateDropZone, candidateFileInput, files => {
    Array.from(files).forEach(processCandidateFile);
});

async function processCandidateFile(file) {
    if (file.name.endsWith('.json')) {
        const reader = new FileReader();
        reader.onload = e => {
            try {
                const data = JSON.parse(e.target.result);
                let cands = data.candidates || data.data || data;
                if (!Array.isArray(cands)) cands = [cands];
                cands.forEach(c => {
                    uploadedCandidates.push(c);
                    addCandidateRow(c.name || 'Unknown Candidate', file.name, 'ok');
                });
                updateCandidateCount();
            } catch (err) {
                console.error('Invalid JSON:', err);
            }
        };
        reader.readAsText(file);
        return;
    }

    const rowId = `cand-${Date.now()}-${Math.random().toString(36).slice(2,5)}`;
    addCandidateRow(`Parsing ${file.name}…`, file.name, 'loading', rowId);

    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch('/api/extract-candidate', { method: 'POST', body: fd });
        if (!res.ok) throw new Error();
        const candidate = await res.json();
        uploadedCandidates.push(candidate);
        updateCandidateRow(rowId, candidate.name, 'ok');
        updateCandidateCount();
    } catch {
        updateCandidateRow(rowId, 'Extraction failed', 'error');
    }
}

function addCandidateRow(name, source, status, id = null) {
    const div = document.createElement('div');
    div.className = 'cand-row';
    if (id) div.id = id;

    const initials = name.length >= 2
        ? name.replace('Parsing ','').substring(0,2).toUpperCase()
        : '??';

    div.innerHTML = `
        <div class="cand-av">${initials}</div>
        <div class="cand-nm">${escHtml(name)}</div>
        <div class="cand-src">${escHtml(source)}</div>
        <div class="cand-st ${status}">${statusIcon(status)}</div>
    `;
    candidatesPreviewList.appendChild(div);
}

function updateCandidateRow(id, name, status) {
    const div = document.getElementById(id);
    if (!div) return;
    const initials = name.substring(0,2).toUpperCase();
    div.querySelector('.cand-av').textContent = initials;
    div.querySelector('.cand-nm').textContent = name;
    div.querySelector('.cand-st').className   = `cand-st ${status}`;
    div.querySelector('.cand-st').innerHTML   = statusIcon(status);
}

function statusIcon(s) {
    if (s === 'ok')      return '<i class="fa-solid fa-circle-check"></i>';
    if (s === 'loading') return '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    if (s === 'error')   return '<i class="fa-solid fa-triangle-exclamation"></i>';
    return '';
}

function updateCandidateCount() {
    const n = uploadedCandidates.length;
    candidateCountBadge.textContent = n;
    candidateCountBadge.classList.toggle('has-data', n > 0);
    clearCandidatesBtn.classList.toggle('hidden', n === 0);
}

if (clearCandidatesBtn) {
    clearCandidatesBtn.addEventListener('click', () => {
        uploadedCandidates = [];
        candidatesPreviewList.innerHTML = '';
        updateCandidateCount();
    });
}

// ── Run Ranking ──
runBtn.addEventListener('click', async () => {
    hideError();

    const textTabActive = document.getElementById('tab-text')?.classList.contains('active');
    const finalJd = textTabActive ? jdRawText.value.trim() : rawJdText.trim();

    if (!finalJd || finalJd.length < 50) {
        showError('Please provide a Job Description of at least 50 characters.');
        return;
    }
    if (uploadedCandidates.length === 0) {
        showError('Please upload at least one candidate (JSON dataset or resume files).');
        return;
    }

    const shortlistSize = Math.min(Math.max(parseInt(shortlistSizeInput.value, 10) || 10, 1), 50);

    // Show results section + loading
    sectionResults.classList.remove('hidden');
    loadingState.classList.remove('hidden');
    rankingResults.innerHTML = '';
    loadingTextEl.textContent = 'Extracting intelligence from job description…';
    runBtn.disabled = true;

    // Scroll results into view
    setTimeout(() => sectionResults.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);

    // Unlock nav link
    if (navResultsLink) {
        navResultsLink.style.opacity = '1';
        navResultsLink.style.pointerEvents = 'auto';
    }

    try {
        loadingTextEl.textContent = 'Scoring and ranking candidates semantically…';

        const res = await fetch('/api/rank-candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                raw_jd_text: finalJd,
                candidates: uploadedCandidates,
                shortlist_size: shortlistSize,
            }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(
                err?.detail?.message || err?.detail || `Server error ${res.status}`
            );
        }

        const result = await res.json();
        showExtractionPanel(result);

        await delay(900);

        loadingState.classList.add('hidden');
        runBtn.disabled = false;

        const total = result.total_candidates_evaluated;
        const shown = result.shortlist.length;
        const disq  = result.disqualified_count;
        resultsMeta.innerHTML = `<strong>${total}</strong> evaluated &nbsp;·&nbsp; <strong>${shown}</strong> shortlisted &nbsp;·&nbsp; <strong>${disq}</strong> disqualified`;

        renderRanking(result.shortlist);
        rankedResults = result.shortlist;
        downloadBtn.disabled = false;

    } catch (err) {
        loadingState.classList.add('hidden');
        runBtn.disabled = false;
        showError(err.message || 'Ranking failed. Check server connection.');
    }
});

// ── Render Rankings ──
function renderRanking(shortlist) {
    const tpl = document.getElementById('candidate-card-tpl');
    rankingResults.innerHTML = '';

    shortlist.forEach((c, idx) => {
        const clone = tpl.content.cloneNode(true);
        const card  = clone.querySelector('.result-card');

        // Rank classes
        if (c.rank === 1) card.classList.add('rank-1');
        else if (c.rank === 2) card.classList.add('rank-2');
        else if (c.rank === 3) card.classList.add('rank-3');
        if (c.disqualifiers_hit?.length) card.classList.add('disqualified');

        clone.querySelector('.rc-rank-num').textContent = `#${c.rank}`;

        // Ring score
        const arc = clone.querySelector('.rr-arc');
        const rVal = clone.querySelector('.rc-ring-val');
        const score = Math.max(0, c.total_score);
        const circumference = 169.6;
        const offset = circumference - (circumference * (score / 100));
        setTimeout(() => { arc.style.strokeDashoffset = offset; }, 60 + idx * 30);
        rVal.textContent = Math.round(score);

        // Identity
        const initials = c.name.substring(0,2).toUpperCase();
        clone.querySelector('.rcb-avatar').textContent = initials;
        clone.querySelector('.rcb-name').textContent = c.name;
        clone.querySelector('.rcb-id').textContent   = c.candidate_id || `—`;
        clone.querySelector('.rcb-pts').textContent  = score.toFixed(1);
        clone.querySelector('.rcb-note').textContent = c.recruiter_note;

        // Bars
        const sb = c.score_breakdown;
        setBar(clone, '.rf-skills', '.skills-pts', sb.must_have_skills_score, 40);
        setBar(clone, '.rf-exp',    '.exp-pts',    sb.experience_score,       20);
        setBar(clone, '.rf-nice',   '.nice-pts',   sb.nice_to_have_score,     15);
        setBar(clone, '.rf-beh',    '.beh-pts',    sb.behavioral_score,       10);

        // Tags
        renderTags(clone, '.matched-skills', c.matched_must_have_skills);

        if (c.missing_must_have_skills?.length) {
            renderTags(clone, '.missing-skills', c.missing_must_have_skills);
        } else {
            clone.querySelector('.missing-rtg').classList.add('hidden');
        }

        if (c.disqualifiers_hit?.length) {
            renderTags(clone, '.disq-skills', c.disqualifiers_hit);
            clone.querySelector('.disq-rtg').classList.remove('hidden');
        }

        card.style.animationDelay = `${idx * 75}ms`;
        rankingResults.appendChild(clone);
    });
}

function setBar(clone, barSel, ptsSel, value, max) {
    const pct = Math.min(Math.max((value / max) * 100, 0), 100);
    clone.querySelector(barSel).style.width  = `${pct}%`;
    clone.querySelector(ptsSel).textContent  = `${value.toFixed(1)} / ${max}`;
}

function renderTags(clone, sel, items) {
    const c = clone.querySelector(sel);
    if (!items?.length) {
        c.innerHTML = `<span style="background:transparent;border:none;padding:0;color:rgba(255,255,255,.3)">None</span>`;
        return;
    }
    c.innerHTML = items.map(s => `<span>${escHtml(s)}</span>`).join('');
}

// ── Show Extraction Panel ──
function showExtractionPanel(result) {
    if (!result?.must_have_skills) return;
    extractionPanel.classList.remove('hidden');
    document.getElementById('ep-title').textContent = result.job_title || '—';
    document.getElementById('ep-exp').textContent   = result.minimum_years_experience || 0;

    const mustEl = document.getElementById('ep-must-have');
    mustEl.innerHTML = (result.must_have_skills || [])
        .map(s => `<span>${escHtml(s)}</span>`).join('');

    const disqEl = document.getElementById('ep-disqualifiers');
    if (result.disqualifiers?.length) {
        disqEl.innerHTML = result.disqualifiers.map(s => `<span>${escHtml(s)}</span>`).join('');
    } else {
        disqEl.innerHTML = `<span style="background:transparent;border:none;padding:0;color:rgba(255,255,255,.3)">None stated</span>`;
    }
}

// ── CSV Download ──
downloadBtn.addEventListener('click', () => {
    if (!rankedResults.length) return;

    const headers = [
        'Rank','Name','Score',
        'Core Skills Score','Exp Score','Nice-to-Have Score',
        'Behavioral Score','Location Score','Notice Period Score','Disq Penalty',
        'Matched Skills','Missing Skills','Disqualifiers','Note'
    ];
    const rows = rankedResults.map(c => {
        const sb = c.score_breakdown;
        return [
            c.rank,
            `"${c.name}"`,
            c.total_score.toFixed(1),
            sb.must_have_skills_score,
            sb.experience_score,
            sb.nice_to_have_score,
            sb.behavioral_score,
            sb.location_score,
            sb.notice_period_score,
            sb.disqualifier_penalty,
            `"${(c.matched_must_have_skills || []).join('; ')}"`,
            `"${(c.missing_must_have_skills || []).join('; ')}"`,
            `"${(c.disqualifiers_hit || []).join('; ')}"`,
            `"${c.recruiter_note.replace(/"/g,'""')}"`,
        ];
    });

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), {
        href: url, download: 'ai_recruiter_results.csv'
    });
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

// ── Helpers ──
function setStatus(el, type, html) {
    el.className  = `status-bar ${type}`;
    el.innerHTML  = html;
}
function showError(msg) {
    errorText.textContent = msg;
    errorBanner.classList.remove('hidden');
}
function hideError() {
    errorBanner.classList.add('hidden');
}
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }
function escHtml(str) {
    return String(str)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;');
}
