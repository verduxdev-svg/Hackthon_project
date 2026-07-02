

'use strict';


let rawJdText = '';
let uploadedCandidates = [];
let rankedResults = [];


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


function closeMobileMenu() {
    mobileDrawer.classList.add('hidden');
}


if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', () => {
        mobileDrawer.classList.toggle('hidden');
    });
}


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


document.querySelectorAll('.tsw-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tsw-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.tab).classList.add('active');
        checkStep1Complete();
    });
});


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

    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch('/api/extract-jd/file', { method: 'POST', body: fd });
        if (!res.ok) {
            let errMsg = `Server error ${res.status}`;
            try {
                const errBody = await res.json();
                // Handle FastAPI detail which can be a string or object
                if (typeof errBody.detail === 'string') {
                    errMsg = errBody.detail;
                } else if (errBody.detail?.message) {
                    errMsg = errBody.detail.message;
                } else if (errBody.message) {
                    errMsg = errBody.message;
                }
            } catch { /* ignore parse error on error body */ }

            if (res.status === 429) {
                setStatus(jdFileStatus, 'error', `<i class="fa-solid fa-clock"></i> Rate limited — please wait a moment and try again`);
            } else if (res.status === 502) {
                setStatus(jdFileStatus, 'error', `<i class="fa-solid fa-hourglass-half"></i> AI quota exhausted across all models — wait 1-2 minutes and try again`);
            } else {
                setStatus(jdFileStatus, 'error', `<i class="fa-solid fa-triangle-exclamation"></i> ${errMsg}`);
            }
            return;
        }
        const result = await res.json();

        rawJdText = result.extracted_raw_text || '';

        setStatus(jdFileStatus, 'success', `<i class="fa-solid fa-circle-check"></i> ${file.name} — intelligence extracted`);
        showExtractionPanel(result);
    } catch (err) {
        setStatus(jdFileStatus, 'error', `<i class="fa-solid fa-triangle-exclamation"></i> Failed to parse file — ${err.message || 'Network error'}`);
    }
}



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
                let count = 0;
                cands.forEach(c => {
                    normalizeCandidateJS(c);
                    uploadedCandidates.push(c);
                    count++;
                });
                addCandidateRow(`Loaded ${count} candidates`, file.name, 'ok');
                updateCandidateCount();
            } catch (err) {
                console.error('Invalid JSON:', err);
                addCandidateRow('Failed parsing JSON file', file.name, 'error');
            }
        };
        reader.readAsText(file);
        return;
    }

    if (file.name.endsWith('.jsonl')) {
        const reader = new FileReader();
        reader.onload = e => {
            try {
                const lines = e.target.result.split('\n');
                let count = 0;
                lines.forEach(line => {
                    if (line.trim()) {
                        const c = JSON.parse(line);
                        normalizeCandidateJS(c);
                        uploadedCandidates.push(c);
                        count++;
                    }
                });
                addCandidateRow(`Loaded ${count} candidates`, file.name, 'ok');
                updateCandidateCount();
            } catch (err) {
                console.error('Invalid JSONL:', err);
                addCandidateRow('Failed parsing JSONL file', file.name, 'error');
            }
        };
        reader.readAsText(file);
        return;
    }

    if (file.name.endsWith('.csv')) {
        const reader = new FileReader();
        reader.onload = e => {
            try {
                const text = e.target.result;
                const candidates = parseCSV(text);
                candidates.forEach(c => {
                    normalizeCandidateJS(c);
                    uploadedCandidates.push(c);
                });
                addCandidateRow(`Loaded ${candidates.length} candidates`, file.name, 'ok');
                updateCandidateCount();
            } catch (err) {
                console.error('Invalid CSV:', err);
                addCandidateRow('Failed parsing CSV file', file.name, 'error');
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

    const shortlistSize = Math.min(Math.max(parseInt(shortlistSizeInput.value, 10) || 10, 1), 10000);

    sectionResults.classList.remove('hidden');
    loadingState.classList.remove('hidden');
    rankingResults.innerHTML = '';
    loadingTextEl.textContent = 'Extracting intelligence from job description…';
    runBtn.disabled = true;

    setTimeout(() => sectionResults.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);

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


function renderRanking(shortlist) {
    const tpl = document.getElementById('candidate-card-tpl');
    rankingResults.innerHTML = '';

    shortlist.forEach((c, idx) => {
        const clone = tpl.content.cloneNode(true);
        const card  = clone.querySelector('.result-card');

        if (c.rank === 1) card.classList.add('rank-1');
        else if (c.rank === 2) card.classList.add('rank-2');
        else if (c.rank === 3) card.classList.add('rank-3');
        if (c.disqualifiers_hit?.length) card.classList.add('disqualified');

        clone.querySelector('.rc-rank-num').textContent = `#${c.rank}`;

        const arc = clone.querySelector('.rr-arc');
        const rVal = clone.querySelector('.rc-ring-val');
        const score = Math.max(0, c.total_score);
        const circumference = 169.6;
        const offset = circumference - (circumference * (score / 100));
        setTimeout(() => { arc.style.strokeDashoffset = offset; }, 60 + idx * 30);
        rVal.textContent = Math.round(score);

        const initials = c.name.substring(0,2).toUpperCase();
        clone.querySelector('.rcb-avatar').textContent = initials;
        clone.querySelector('.rcb-name').textContent = c.name;
        clone.querySelector('.rcb-id').textContent   = c.candidate_id || `—`;
        clone.querySelector('.rcb-pts').textContent  = score.toFixed(1);
        clone.querySelector('.rcb-note').textContent = c.recruiter_note;

        const sb = c.score_breakdown;
        setBar(clone, '.rf-skills', '.skills-pts', sb.must_have_skills_score, 40);
        setBar(clone, '.rf-exp',    '.exp-pts',    sb.experience_score,       20);
        setBar(clone, '.rf-nice',   '.nice-pts',   sb.nice_to_have_score,     15);
        setBar(clone, '.rf-beh',    '.beh-pts',    sb.behavioral_score,       10);

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

function parseCSV(text) {
    const lines = [];
    let row = [""];
    let inQuotes = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        const next = text[i+1];
        if (c === '"') {
            if (inQuotes && next === '"') {
                row[row.length - 1] += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (c === ',' && !inQuotes) {
            row.push('');
        } else if ((c === '\r' || c === '\n') && !inQuotes) {
            if (c === '\r' && next === '\n') {
                i++;
            }
            lines.push(row);
            row = [''];
        } else {
            row[row.length - 1] += c;
        }
    }
    if (row.length > 1 || row[0] !== '') {
        lines.push(row);
    }
    if (lines.length === 0) return [];
    const headers = lines[0].map(h => h.trim());
    const candidates = [];
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        if (line.length < headers.length) continue;
        const candidate = {};
        const profile = {};
        const redrob_signals = {};
        const skills = [];
        const career_history = [];
        for (let j = 0; j < headers.length; j++) {
            const col = headers[j];
            let val = line[j];
            if (val === undefined || val === null) continue;
            val = val.trim();
            if (val === "") continue;
            let parsedVal = null;
            if ((val.startsWith('{') && val.endsWith('}')) || (val.startsWith('[') && val.endsWith(']'))) {
                try {
                    parsedVal = JSON.parse(val);
                } catch (e) {}
            }
            if (parsedVal !== null) {
                if (col === 'profile') Object.assign(profile, parsedVal);
                else if (col === 'redrob_signals') Object.assign(redrob_signals, parsedVal);
                else if (col === 'skills' && Array.isArray(parsedVal)) skills.push(...parsedVal);
                else if (col === 'career_history' && Array.isArray(parsedVal)) career_history.push(...parsedVal);
                else candidate[col] = parsedVal;
                continue;
            }
            if (col.includes('.')) {
                const parts = col.split('.');
                const parent = parts[0];
                const child = parts[1];
                if (parent === 'profile') profile[child] = parseValJS(val);
                else if (parent === 'redrob_signals') redrob_signals[child] = parseValJS(val);
                continue;
            }
            if (['candidate_id', 'name', 'summary'].includes(col)) {
                candidate[col] = val;
            } else if (col === 'skills') {
                const delim = val.includes(';') ? ';' : ',';
                const items = val.split(delim).map(s => s.trim()).filter(s => s);
                items.forEach(s => {
                    skills.push({ name: s, proficiency: 'intermediate', years: 0.0 });
                });
            } else if (col === 'profile_location') {
                profile.location = val;
            } else if (col === 'years_of_experience') {
                const num = parseFloat(val);
                if (!isNaN(num)) profile.years_of_experience = num;
            } else if (col === 'willing_to_relocate') {
                profile.willing_to_relocate = ['true', '1', 'yes', 'y'].includes(val.toLowerCase());
            } else if (col === 'current_industry') {
                profile.current_industry = val;
            } else if (col === 'education_tier') {
                profile.education_tier = val;
            } else if (col === 'notice_period_days') {
                const num = parseInt(val, 10);
                if (!isNaN(num)) redrob_signals.notice_period_days = num;
            } else if (col === 'open_to_work') {
                redrob_signals.open_to_work_flag = ['true', '1', 'yes', 'y'].includes(val.toLowerCase());
            } else {
                candidate[col] = parseValJS(val);
            }
        }
        if (Object.keys(profile).length > 0) candidate.profile = profile;
        if (Object.keys(redrob_signals).length > 0) candidate.redrob_signals = redrob_signals;
        if (skills.length > 0) candidate.skills = skills;
        if (career_history.length > 0) candidate.career_history = career_history;
        candidates.push(candidate);
    }
    return candidates;
}

function parseValJS(val) {
    const lower = val.toLowerCase();
    if (['true', 'yes', 'y'].includes(lower)) return true;
    if (['false', 'no', 'n'].includes(lower)) return false;
    const num = Number(val);
    if (!isNaN(num)) return num;
    return val;
}

function normalizeCandidateJS(c) {
    if (!c.name && c.profile) {
        c.name = c.profile.anonymized_name || c.profile.name || "Unknown Candidate";
    }
    if (!c.name) c.name = "Unknown Candidate";
    if (c.skills && Array.isArray(c.skills)) {
        c.skills.forEach(s => {
            if (s.years === undefined && s.duration_months !== undefined) {
                s.years = parseFloat((s.duration_months / 12.0).toFixed(2));
            }
        });
    }
    if (c.profile && c.redrob_signals && c.profile.willing_to_relocate === undefined) {
        if (c.redrob_signals.willing_to_relocate !== undefined) {
            c.profile.willing_to_relocate = c.redrob_signals.willing_to_relocate;
        }
    }
    if (c.profile && c.education && Array.isArray(c.education) && c.education.length > 0) {
        if (c.profile.education_tier === undefined && c.education[0].tier !== undefined) {
            c.profile.education_tier = c.education[0].tier;
        }
    }
    if (c.redrob_signals && c.redrob_signals.last_active_days_ago === undefined) {
        const activeDateStr = c.redrob_signals.last_active_date;
        if (activeDateStr) {
            try {
                const activeDate = new Date(activeDateStr);
                const today = new Date("2026-07-01");
                const diffTime = today - activeDate;
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                c.redrob_signals.last_active_days_ago = Math.max(0, diffDays);
            } catch (e) {}
        }
    }
    return c;
}