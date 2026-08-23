/* Cosmos Strategy Platform Core Javascript Logic */

const API_BASE = window.location.origin;

// State management
let state = {
    cases: [],
    currentCase: null,
    currentLevelIndex: 0,
    completedLevels: {}, // maps level ID -> true
    evaluations: {} // maps level ID -> evaluation results
};

// UI Elements
const statusIndicator = document.querySelector('#backend-status .status-indicator');
const statusLabel = document.querySelector('#backend-status .status-label');
const screenCaseSelection = document.getElementById('screen-case-selection');
const screenWorkspace = document.getElementById('screen-workspace');
const casesListContainer = document.getElementById('cases-list-container');
const levelsMenuContainer = document.getElementById('levels-menu-container');
const currentCaseTitle = document.getElementById('current-case-title');
const currentCaseSubtitle = document.getElementById('current-case-subtitle');
const currentCaseContext = document.getElementById('current-case-context');
const currentLevelBadge = document.getElementById('current-level-badge');
const currentQuestionText = document.getElementById('current-question-text');
const userAnswerInput = document.getElementById('user-answer-input');
const charCountSpan = document.getElementById('char-count');
const btnSubmitAnswer = document.getElementById('btn-submit-answer');
const btnPrevLevel = document.getElementById('btn-prev-level');
const btnNextLevel = document.getElementById('btn-next-level');
const btnBackToCases = document.getElementById('btn-back-to-cases');
const caseContextCard = document.getElementById('case-context-card');
const btnToggleContext = document.getElementById('btn-toggle-context');
const btnToggleReferences = document.getElementById('btn-toggle-references');
const referencesContainer = document.getElementById('references-container');

// Results elements
const evaluationResults = document.getElementById('evaluation-results');
const ratingContainer = document.getElementById('rating-container');
const ratingValue = document.getElementById('rating-value');
const ratingIcon = document.getElementById('rating-icon');
const critiqueContent = document.getElementById('critique-content');
const recommendationsContent = document.getElementById('recommendations-content');
const referencesList = document.getElementById('references-container');

// Initialize Platform
document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
    loadCases();
    setupEventListeners();
});

// Check API and Bedrock Connection Status
async function checkStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        if (response.ok) {
            const data = await response.json();
            statusIndicator.className = 'status-indicator online';
            statusLabel.textContent = data.aws_connected ? 'AWS Bedrock Connected' : 'Local Fallback Engine Active';
        } else {
            setOfflineStatus();
        }
    } catch (err) {
        setOfflineStatus();
    }
}

function setOfflineStatus() {
    statusIndicator.className = 'status-indicator offline';
    statusLabel.textContent = 'Server Offline';
}

// Load Cases from Backend
async function loadCases() {
    try {
        const response = await fetch(`${API_BASE}/api/cases`);
        if (response.ok) {
            state.cases = await response.json();
            renderCases();
        } else {
            casesListContainer.innerHTML = '<div class="loading-spinner"><i class="fa-solid fa-circle-exclamation"></i> Error loading case studies.</div>';
        }
    } catch (err) {
        console.error("Failed loading cases:", err);
        casesListContainer.innerHTML = '<div class="loading-spinner"><i class="fa-solid fa-circle-exclamation"></i> Could not connect to API server.</div>';
    }
}

// Render Cases Selection Grid
function renderCases() {
    casesListContainer.innerHTML = '';
    state.cases.forEach(c => {
        const card = document.createElement('div');
        card.className = 'glass-card case-card animate-slide-up';
        card.innerHTML = `
            <h3>${c.title}</h3>
            <div class="case-subtitle">${c.subtitle}</div>
            <p>${c.description}</p>
            <div class="case-card-footer">
                <span>Begin Strategy Workshop</span>
                <i class="fa-solid fa-arrow-right"></i>
            </div>
        `;
        card.addEventListener('click', () => selectCase(c.id));
        casesListContainer.appendChild(card);
    });
}

// Action: Select Case
async function selectCase(caseId) {
    try {
        const response = await fetch(`${API_BASE}/api/case/${caseId}`);
        if (response.ok) {
            state.currentCase = await response.json();
            state.currentLevelIndex = 0;
            state.completedLevels = {};
            state.evaluations = {};
            
            // Switch Screen
            screenCaseSelection.classList.remove('active');
            screenWorkspace.classList.add('active');
            
            // Render details
            currentCaseTitle.textContent = state.currentCase.title;
            currentCaseSubtitle.textContent = state.currentCase.subtitle;
            currentCaseContext.innerHTML = `<p>${state.currentCase.context}</p>`;
            
            // Collapsed context by default
            caseContextCard.classList.add('collapsed');
            
            renderLevelsSidebar();
            loadCurrentQuestion();
        }
    } catch (err) {
        console.error("Error selecting case:", err);
    }
}

// Render Levels Sidebar
function renderLevelsSidebar() {
    levelsMenuContainer.innerHTML = '';
    state.currentCase.questions.forEach((q, idx) => {
        const item = document.createElement('div');
        item.className = 'level-item';
        if (idx === state.currentLevelIndex) item.classList.add('active');
        if (state.completedLevels[q.id]) item.classList.add('completed');
        
        item.innerHTML = `
            <div class="level-info">
                <span class="level-num">Level ${idx + 1}</span>
                <span class="level-name">${q.level.split(': ')[1]}</span>
            </div>
            <span class="level-status-icon">
                <i class="${state.completedLevels[q.id] ? 'fa-solid fa-circle-check' : 'fa-regular fa-circle'}"></i>
            </span>
        `;
        item.addEventListener('click', () => changeLevel(idx));
        levelsMenuContainer.appendChild(item);
    });
}

// Load Question at current active Index
function loadCurrentQuestion() {
    const questionObj = state.currentCase.questions[state.currentLevelIndex];
    currentLevelBadge.textContent = questionObj.level;
    currentQuestionText.textContent = questionObj.question;
    
    // Clear/Reload answer textarea
    const savedAnswer = state.evaluations[questionObj.id]?.user_answer || "";
    userAnswerInput.value = savedAnswer;
    updateCharCounter();
    
    // Toggle Prev/Next buttons
    btnPrevLevel.disabled = (state.currentLevelIndex === 0);
    btnNextLevel.disabled = (state.currentLevelIndex === state.currentCase.questions.length - 1);
    
    // Show evaluation results if already evaluated
    if (state.evaluations[questionObj.id]) {
        showEvaluationResults(state.evaluations[questionObj.id]);
    } else {
        evaluationResults.classList.add('hidden');
    }
}

// Change level index
function changeLevel(index) {
    if (index >= 0 && index < state.currentCase.questions.length) {
        state.currentLevelIndex = index;
        renderLevelsSidebar();
        loadCurrentQuestion();
    }
}

// Update Character Counter
function updateCharCounter() {
    const count = userAnswerInput.value.length;
    charCountSpan.textContent = `${count} characters`;
    btnSubmitAnswer.disabled = (count < 10);
}

// Event Listeners
function setupEventListeners() {
    // Back button
    btnBackToCases.addEventListener('click', () => {
        screenWorkspace.classList.remove('active');
        screenCaseSelection.classList.add('active');
        checkStatus();
    });

    // Character counter check
    userAnswerInput.addEventListener('input', updateCharCounter);

    // Form Submit (Evaluate Answer)
    btnSubmitAnswer.addEventListener('click', submitAnswerEvaluation);

    // Prev/Next buttons
    btnPrevLevel.addEventListener('click', () => changeLevel(state.currentLevelIndex - 1));
    btnNextLevel.addEventListener('click', () => changeLevel(state.currentLevelIndex + 1));

    // Collapse toggles
    btnToggleContext.addEventListener('click', () => {
        caseContextCard.classList.toggle('collapsed');
    });

    btnToggleReferences.addEventListener('click', () => {
        referencesContainer.classList.toggle('collapsed');
    });
}

// Submit Answer for RAG critique
async function submitAnswerEvaluation() {
    const questionObj = state.currentCase.questions[state.currentLevelIndex];
    const answerText = userAnswerInput.value.strip ? userAnswerInput.value.strip() : userAnswerInput.value;

    btnSubmitAnswer.classList.add('loading');
    btnSubmitAnswer.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                case_id: state.currentCase.id,
                question_id: questionObj.id,
                question_text: questionObj.question,
                user_answer: answerText
            })
        });

        if (response.ok) {
            const data = await response.json();
            
            // Store evaluation in state
            state.evaluations[questionObj.id] = {
                user_answer: answerText,
                ...data
            };
            
            // Mark level completed
            state.completedLevels[questionObj.id] = true;
            
            // Render results
            showEvaluationResults(data);
            renderLevelsSidebar();
        } else {
            alert("Error invoking evaluation API. Please ensure python server logs are healthy.");
        }
    } catch (err) {
        console.error("Evaluation request failed:", err);
        alert("Failed to reach API server. Ensure backend/main.py is running.");
    } finally {
        btnSubmitAnswer.classList.remove('loading');
        btnSubmitAnswer.disabled = false;
    }
}

// Show Evaluation Result Cards in UI
function showEvaluationResults(data) {
    evaluationResults.classList.remove('hidden');
    
    // Rating classes mapping
    ratingContainer.className = 'glass-card rating-card';
    let iconClass = 'fa-solid fa-circle-exclamation';
    
    if (data.rating.includes('Level 1')) {
        ratingContainer.classList.add('lvl-1');
        iconClass = 'fa-solid fa-triangle-exclamation';
    } else if (data.rating.includes('Level 2')) {
        ratingContainer.classList.add('lvl-2');
        iconClass = 'fa-solid fa-circle-chevron-up';
    } else if (data.rating.includes('Level 3')) {
        ratingContainer.classList.add('lvl-3');
        iconClass = 'fa-solid fa-circle-check';
    }

    ratingIcon.innerHTML = `<i class="${iconClass}"></i>`;
    ratingValue.textContent = data.rating;
    
    critiqueContent.textContent = data.critique;
    recommendationsContent.textContent = data.recommendations;
    
    // Render Source slides retrieved by RAG
    referencesList.innerHTML = '';
    
    if (data.source_slides && data.source_slides.length > 0) {
        data.source_slides.forEach(slide => {
            const item = document.createElement('div');
            item.className = 'reference-item';
            item.innerHTML = `
                <div class="ref-meta">
                    <span class="ref-source">${slide.source_file} (Page/Slide ${slide.slide_number})</span>
                    <span class="ref-score"><i class="fa-solid fa-chart-simple"></i> Match: ${(slide.score * 100).toFixed(1)}%</span>
                </div>
                <div class="ref-text">"${slide.text}"</div>
            `;
            referencesList.appendChild(item);
        });
        btnToggleReferences.parentElement.classList.remove('hidden');
    } else {
        btnToggleReferences.parentElement.classList.add('hidden');
    }

    // Scroll to results automatically
    evaluationResults.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
