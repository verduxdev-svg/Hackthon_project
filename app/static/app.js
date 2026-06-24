// State
let rawJdText = "";
let uploadedCandidates = [];
let rankedResults = [];

// DOM Elements
const tabs = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const jdDropZone = document.getElementById('jd-drop-zone');
const jdFileInput = document.getElementById('jd-file-input');
const jdFileName = document.getElementById('jd-file-name');
const jdRawText = document.getElementById('jd-raw-text');

const candidateDropZone = document.getElementById('candidate-drop-zone');
const candidateFileInput = document.getElementById('candidate-file-input');
const candidatesPreviewList = document.getElementById('candidates-preview-list');
const candidateCountBadge = document.getElementById('candidate-count-badge');

const runBtn = document.getElementById('run-ranking-btn');
const downloadBtn = document.getElementById('download-csv-btn');

// Panels
const extractionPanel = document.getElementById('extraction-panel');
const rankingPanel = document.getElementById('ranking-panel');
const loadingOverlay = document.getElementById('loading-overlay');
const rankingResults = document.getElementById('ranking-results');

// Setup Tabs
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        tab.classList.add('active');
        document.getElementById(tab.dataset.target).classList.add('active');
    });
});

// Setup JD Drop Zone
jdDropZone.addEventListener('click', (e) => {
    if(e.target.tagName !== 'BUTTON') jdFileInput.click();
});

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    jdDropZone.addEventListener(eventName, preventDefaults, false);
});

['dragenter', 'dragover'].forEach(eventName => {
    jdDropZone.addEventListener(eventName, () => jdDropZone.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    jdDropZone.addEventListener(eventName, () => jdDropZone.classList.remove('dragover'), false);
});

jdDropZone.addEventListener('drop', handleJdDrop, false);
jdFileInput.addEventListener('change', function() {
    if(this.files && this.files.length > 0) processJdFile(this.files[0]);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function handleJdDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if(files.length > 0) processJdFile(files[0]);
}

async function processJdFile(file) {
    jdFileName.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Processing ${file.name}...`;
    
    if (file.name.endsWith('.json')) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = JSON.parse(e.target.result);
                rawJdText = data.raw_jd_text || JSON.stringify(data);
                jdFileName.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${file.name} loaded`;
            } catch (err) {
                jdFileName.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:var(--status-danger)"></i> Invalid JSON format`;
            }
        };
        reader.readAsText(file);
    } else {
        const formData = new FormData();
        formData.append("file", file);
        try {
            const response = await fetch('/api/extract-jd/file', {
                method: 'POST',
                body: formData
            });
            if(!response.ok) throw new Error("Failed to process JD file");
            const result = await response.json();
            
            const reader = new FileReader();
            reader.onload = (e) => {
                rawJdText = e.target.result;
                jdFileName.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${file.name} parsed successfully`;
                showExtractionPreview(result);
            };
            reader.readAsText(file);
        } catch(e) {
            jdFileName.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:var(--status-danger)"></i> Error parsing document`;
        }
    }
}

// Setup Candidate Drop Zone
candidateDropZone.addEventListener('click', (e) => {
    if(e.target.tagName !== 'BUTTON') candidateFileInput.click();
});

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    candidateDropZone.addEventListener(eventName, preventDefaults, false);
});

['dragenter', 'dragover'].forEach(eventName => {
    candidateDropZone.addEventListener(eventName, () => candidateDropZone.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    candidateDropZone.addEventListener(eventName, () => candidateDropZone.classList.remove('dragover'), false);
});

candidateDropZone.addEventListener('drop', handleCandidateDrop, false);
candidateFileInput.addEventListener('change', function() {
    if(this.files && this.files.length > 0) Array.from(this.files).forEach(processCandidateFile);
});

function handleCandidateDrop(e) {
    const dt = e.dataTransfer;
    Array.from(dt.files).forEach(processCandidateFile);
}

async function processCandidateFile(file) {
    if (file.name.endsWith('.json')) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = JSON.parse(e.target.result);
                let cands = data.candidates || data.data || data;
                if(!Array.isArray(cands)) cands = [cands];
                
                cands.forEach(c => {
                    uploadedCandidates.push(c);
                    renderCandidatePreview(c.name || "Unknown Candidate", file.name);
                });
                updateCandidateCount();
            } catch (err) {
                console.error("Invalid JSON", err);
            }
        };
        reader.readAsText(file);
    } else if (file.name.endsWith('.docx') || file.name.endsWith('.txt')) {
        const id = "cand-" + Date.now() + "-" + Math.floor(Math.random() * 1000);
        renderCandidatePreview(`Parsing ${file.name}...`, file.name, id, true);
        
        const formData = new FormData();
        formData.append("file", file);
        try {
            const response = await fetch('/api/extract-candidate', {
                method: 'POST',
                body: formData
            });
            if(!response.ok) throw new Error("Failed to extract candidate");
            const candidate = await response.json();
            uploadedCandidates.push(candidate);
            updateCandidatePreview(id, candidate.name, true);
            updateCandidateCount();
        } catch(e) {
            updateCandidatePreview(id, "Extraction Failed", false);
        }
    }
}

function renderCandidatePreview(name, source, id=null, loading=false) {
    const div = document.createElement('div');
    div.className = 'candidate-preview-item';
    if(id) div.id = id;
    
    div.innerHTML = `
        <div class="cand-info">
            ${loading ? '<i class="fa-solid fa-circle-notch fa-spin" style="color:var(--accent-primary)"></i>' : '<i class="fa-solid fa-user-astronaut" style="color:var(--text-secondary)"></i>'}
            <span class="cand-name">${name}</span>
        </div>
        <span class="cand-source">${source}</span>
    `;
    candidatesPreviewList.appendChild(div);
}

function updateCandidatePreview(id, newName, success) {
    const div = document.getElementById(id);
    if(div) {
        if(success) {
            div.querySelector('.cand-info').innerHTML = `<i class="fa-solid fa-circle-check" style="color:var(--status-success)"></i> <span class="cand-name">${newName}</span>`;
        } else {
            div.querySelector('.cand-info').innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:var(--status-danger)"></i> <span class="cand-name">${newName}</span>`;
        }
    }
}

function updateCandidateCount() {
    candidateCountBadge.innerText = `${uploadedCandidates.length} Loaded`;
    candidateCountBadge.style.background = 'rgba(0, 240, 255, 0.2)';
    candidateCountBadge.style.color = 'var(--accent-primary)';
}

// Run Ranking
runBtn.addEventListener('click', async () => {
    let finalJdText = rawJdText;
    if (document.querySelector('.tab-btn[data-target="jd-text"]').classList.contains('active')) {
        finalJdText = jdRawText.value;
    }

    if (!finalJdText || finalJdText.length < 50) {
        alert("Please provide a valid Job Description (at least 50 characters).");
        return;
    }

    if (uploadedCandidates.length === 0) {
        alert("Please upload at least one candidate (JSON or Resume).");
        return;
    }

    rankingResults.innerHTML = '';
    loadingOverlay.classList.remove('hidden');
    extractionPanel.classList.add('hidden');
    document.getElementById('ranking-controls').classList.remove('hidden');
    document.getElementById('total-evaluated').innerText = `${uploadedCandidates.length} Evaluated`;

    try {
        const response = await fetch('/api/rank-candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                raw_jd_text: finalJdText,
                candidates: uploadedCandidates,
                shortlist_size: uploadedCandidates.length
            })
        });

        if(!response.ok) throw new Error("Ranking failed");
        const result = await response.json();
        
        showExtractionPreview(result);

        // Add an artificial delay for visual flair (let the user see the hologram spinner)
        setTimeout(() => {
            loadingOverlay.classList.add('hidden');
            renderRanking(result.shortlist);
            downloadBtn.disabled = false;
            rankedResults = result.shortlist;
        }, 1500);
        
    } catch(e) {
        console.error(e);
        loadingOverlay.classList.add('hidden');
        rankingResults.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon-wrapper" style="color:var(--status-danger)"><i class="fa-solid fa-triangle-exclamation"></i></div>
                <h3>Analysis Failed</h3>
                <p>Could not process the ranking request. Check connection to AI core.</p>
            </div>`;
    }
});

function showExtractionPreview(extractionResult) {
    if(!extractionResult.must_have_skills) return;
    
    extractionPanel.classList.remove('hidden');
    document.getElementById('ext-job-title').innerText = extractionResult.job_title;
    document.getElementById('ext-min-exp').innerText = extractionResult.minimum_years_experience || 0;
    
    document.getElementById('ext-must-have').innerHTML = extractionResult.must_have_skills.map(s => `<span>${s}</span>`).join('');
    
    if(extractionResult.disqualifiers && extractionResult.disqualifiers.length > 0) {
        document.getElementById('ext-disqualifiers').innerHTML = extractionResult.disqualifiers.map(s => `<span>${s}</span>`).join('');
    } else {
        document.getElementById('ext-disqualifiers').innerHTML = `<span style="border-color:rgba(255,255,255,0.1); color:var(--text-muted); background:transparent;">None explicitly stated</span>`;
    }
}
// ui changed 
function renderRanking(shortlist) {
    const template = document.getElementById('candidate-card-template');
    rankingResults.innerHTML = '';

    shortlist.forEach(c => {
        const clone = template.content.cloneNode(true);
        const card = clone.querySelector('.neo-candidate-card');
        
        if(c.rank === 1) card.classList.add('top-rank');
        
        clone.querySelector('.rank-num').innerText = c.rank;
        clone.querySelector('.c-name').innerText = c.name;
        clone.querySelector('.c-score').innerText = c.total_score.toFixed(1);
        clone.querySelector('.recruiter-note').innerText = c.recruiter_note;
        
        clone.querySelector('.skills-pts').innerText = `(${c.score_breakdown.must_have_skills_score.toFixed(1)}/40)`;
        clone.querySelector('.fill-skills').style.width = `${(c.score_breakdown.must_have_skills_score / 40) * 100}%`;
        
        clone.querySelector('.exp-pts').innerText = `(${c.score_breakdown.experience_score.toFixed(1)}/20)`;
        clone.querySelector('.fill-exp').style.width = `${(c.score_breakdown.experience_score / 20) * 100}%`;

        // Match details
        const matchedWrapper = clone.querySelector('.matched-skills');
        if(c.matched_must_have_skills.length > 0) {
            matchedWrapper.innerHTML = c.matched_must_have_skills.map(s => `<span>${s}</span>`).join('');
        } else {
            matchedWrapper.innerHTML = `<span>None</span>`;
            matchedWrapper.parentElement.style.opacity = "0.5";
        }

        const missingWrapper = clone.querySelector('.missing-skills');
        if(c.missing_must_have_skills.length > 0) {
            missingWrapper.innerHTML = c.missing_must_have_skills.map(s => `<span>${s}</span>`).join('');
        } else {
            missingWrapper.parentElement.classList.add('hidden');
        }

        const disqWrapper = clone.querySelector('.disqualified-reasons');
        if(c.disqualifiers_hit && c.disqualifiers_hit.length > 0) {
            disqWrapper.innerHTML = c.disqualifiers_hit.map(s => `<span>${s}</span>`).join('');
            disqWrapper.parentElement.classList.remove('hidden');
            card.style.borderColor = 'rgba(255, 23, 68, 0.4)';
        }

        rankingResults.appendChild(clone);
    });
}

// Download CSV
downloadBtn.addEventListener('click', () => {
    if(rankedResults.length === 0) return;
    
    const headers = ["Rank", "Name", "Score", "Must-Have Match", "Missing Skills", "Disqualifiers", "Note"];
    const rows = rankedResults.map(c => [
        c.rank,
        `"${c.name}"`,
        c.total_score,
        `"${c.matched_must_have_skills.join('; ')}"`,
        `"${c.missing_must_have_skills.join('; ')}"`,
        `"${c.disqualifiers_hit ? c.disqualifiers_hit.join('; ') : ''}"`,
        `"${c.recruiter_note}"`
    ]);
    
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "intelligence_engine_results.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
});
