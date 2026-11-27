(() => {
  "use strict";

  const ARCHIVE_URL = "data/questions.json";
  const SOLVED_KEY = "daily-ext2:solved";
  const ATTEMPT_PREFIX = "daily-ext2:attempt:";
  const PROGRESS_PREFIX = "daily-ext2:progress:";
  const SYDNEY_TIME_ZONE = "Australia/Sydney";

  const elements = {
    todayLabel: document.getElementById("todayLabel"),
    loadingState: document.getElementById("loadingState"),
    questionContent: document.getElementById("questionContent"),
    errorState: document.getElementById("errorState"),
    questionDate: document.getElementById("questionDate"),
    topicChip: document.getElementById("topicChip"),
    targetChip: document.getElementById("targetChip"),
    modeChip: document.getElementById("modeChip"),
    statementText: document.getElementById("statementText"),
    attemptInput: document.getElementById("attemptInput"),
    saveAttemptButton: document.getElementById("saveAttemptButton"),
    markSolvedButton: document.getElementById("markSolvedButton"),
    resetProgressButton: document.getElementById("resetProgressButton"),
    feedback: document.getElementById("feedback"),
    ladderSteps: document.getElementById("ladderSteps"),
    nextHintButton: document.getElementById("nextHintButton"),
    hintOnePanel: document.getElementById("hintOnePanel"),
    hintOneText: document.getElementById("hintOneText"),
    hintTwoPanel: document.getElementById("hintTwoPanel"),
    hintTwoText: document.getElementById("hintTwoText"),
    walkthroughPanel: document.getElementById("walkthroughPanel"),
    walkthroughList: document.getElementById("walkthroughList"),
    knowledgeGapBlock: document.getElementById("knowledgeGapBlock"),
    knowledgeGapText: document.getElementById("knowledgeGapText"),
    formalPanel: document.getElementById("formalPanel"),
    formalList: document.getElementById("formalList"),
    solvedCount: document.getElementById("solvedCount"),
    streakCount: document.getElementById("streakCount"),
    archiveList: document.getElementById("archiveList"),
    appLoading: document.getElementById("appLoading"),
    retryButton: document.getElementById("retryButton")
  };

  const state = {
    archive: [],
    question: null,
    progress: 0,
    solved: readJson(SOLVED_KEY, {})
  };

  function readJson(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value ? JSON.parse(value) : fallback;
    } catch {
      return fallback;
    }
  }

  function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function sydneyDateKey(date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: SYDNEY_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }).formatToParts(date);
    const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${lookup.year}-${lookup.month}-${lookup.day}`;
  }

  function sydneyLongDate(dateKey) {
    const date = new Date(`${dateKey}T12:00:00+11:00`);
    return new Intl.DateTimeFormat("en-AU", {
      timeZone: SYDNEY_TIME_ZONE,
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric"
    }).format(date);
  }

  function normaliseQuestions(payload) {
    const questions = Array.isArray(payload) ? payload : payload.questions;
    return (questions || [])
      .filter((question) => question && question.date && question.statement)
      .map((question) => ({
        ...question,
        id: question.id || `${question.date}-${question.fingerprint || question.topic || "question"}`,
        fingerprint: question.fingerprint || question.id || question.statement
      }))
      .sort((a, b) => b.date.localeCompare(a.date));
  }

  function solvedRecordFor(question) {
    return state.solved[question.id] || null;
  }

  function isDuplicateOfSolved(question) {
    return Object.values(state.solved).some((record) => (
      record &&
      record.fingerprint === question.fingerprint &&
      record.id !== question.id
    ));
  }

  function chooseQuestion(questions) {
    const todayKey = sydneyDateKey();
    const exact = questions.find((question) => question.date === todayKey);
    if (exact && !isDuplicateOfSolved(exact)) return exact;
    return questions.find((question) => !isDuplicateOfSolved(question)) || exact || questions[0];
  }

  function progressKey(question) {
    return `${PROGRESS_PREFIX}${question.id}`;
  }

  function attemptKey(question) {
    return `${ATTEMPT_PREFIX}${question.id}`;
  }

  function readProgress(question) {
    const value = Number(localStorage.getItem(progressKey(question)) || "0");
    return Number.isFinite(value) ? Math.max(0, Math.min(4, value)) : 0;
  }

  function setProgress(question, value) {
    state.progress = Math.max(0, Math.min(4, value));
    localStorage.setItem(progressKey(question), String(state.progress));
    renderProgress();
  }

  function setText(element, value) {
    element.textContent = Array.isArray(value) ? value.join("\n") : String(value || "");
  }

  function replaceList(listElement, items) {
    listElement.replaceChildren();
    const values = Array.isArray(items) ? items : [items].filter(Boolean);
    for (const item of values) {
      const li = document.createElement("li");
      li.textContent = String(item);
      listElement.appendChild(li);
    }
  }

  function renderMetadata(question) {
    const prefix = question.mode === "Sunday Curveball" ? "DAILY EXT 2: SUNDAY CURVEBALL" : "DAILY EXT 2";
    elements.questionDate.textContent = `${prefix}: ${sydneyLongDate(question.date)}`;
    elements.topicChip.textContent = question.topic || "Extension 2";
    elements.targetChip.textContent = question.target || "HSC style";
    elements.modeChip.textContent = question.mode || "Standard";
  }

  function renderQuestion(question) {
    state.question = question;
    state.progress = readProgress(question);

    renderMetadata(question);
    setText(elements.statementText, question.statement);
    setText(elements.hintOneText, question.hint1);
    setText(elements.hintTwoText, question.hint2);
    replaceList(elements.walkthroughList, question.walkthrough);
    replaceList(elements.formalList, question.formalSolution);

    if (question.knowledgeGap) {
      elements.knowledgeGapBlock.hidden = false;
      setText(elements.knowledgeGapText, question.knowledgeGap);
    } else {
      elements.knowledgeGapBlock.hidden = true;
      elements.knowledgeGapText.textContent = "";
    }

    elements.attemptInput.value = localStorage.getItem(attemptKey(question)) || "";
    elements.feedback.textContent = solvedRecordFor(question)
      ? "Solved. You can still review the ladder or reset your local progress."
      : "";
    elements.loadingState.hidden = true;
    elements.errorState.hidden = true;
    elements.questionContent.hidden = false;

    renderProgress();
    renderArchive();
    updateStats();
    updateSolvedButton();
    typesetMath().finally(() => {
      elements.appLoading.hidden = true;
    });
  }

  function renderProgress() {
    const labels = ["Reveal hint 1", "Reveal hint 2", "Reveal walkthrough", "Reveal formal solution", "Ladder complete"];
    elements.hintOnePanel.dataset.open = String(state.progress >= 1);
    elements.hintTwoPanel.dataset.open = String(state.progress >= 2);
    elements.walkthroughPanel.dataset.open = String(state.progress >= 3);
    elements.formalPanel.dataset.open = String(state.progress >= 4);
    elements.nextHintButton.textContent = labels[state.progress];
    elements.nextHintButton.disabled = state.progress >= 4;

    for (const step of elements.ladderSteps.querySelectorAll(".ladder-step")) {
      const index = Number(step.dataset.step);
      step.dataset.complete = String(index <= state.progress);
      step.setAttribute("aria-current", index === state.progress + 1 && state.progress < 4 ? "step" : "false");
    }
    typesetMath();
  }

  function typesetMath() {
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
      return window.MathJax.typesetPromise().catch(() => {});
    }
    return Promise.resolve();
  }

  function updateSolvedButton() {
    elements.markSolvedButton.textContent = state.question && solvedRecordFor(state.question)
      ? "Unmark solved"
      : "Mark as solved";
  }

  function saveAttempt() {
    if (!state.question) return;
    const attempt = elements.attemptInput.value.trim();
    localStorage.setItem(attemptKey(state.question), attempt);
    elements.feedback.textContent = attempt
      ? "Attempt saved. Use the ladder one rung at a time and compare each line before revealing more."
      : "Blank attempt saved.";
  }

  function markSolved() {
    if (!state.question) return;
    const question = state.question;
    const shouldUnmark = Boolean(solvedRecordFor(question));
    state.solved = readJson(SOLVED_KEY, {});
    if (shouldUnmark) {
      delete state.solved[question.id];
      elements.feedback.textContent = "Solved mark removed. Your attempt and hint progress are unchanged.";
    } else {
      state.solved[question.id] = {
        id: question.id,
        fingerprint: question.fingerprint,
        date: question.date,
        solveDate: sydneyDateKey(),
        solvedAt: new Date().toISOString(),
        topic: question.topic || "Extension 2"
      };
      elements.feedback.textContent = "Marked as solved. Its fingerprint is now cached in this browser.";
    }
    writeJson(SOLVED_KEY, state.solved);
    renderArchive();
    updateStats();
    updateSolvedButton();
  }

  function resetProgress() {
    if (!state.question) return;
    if (!window.confirm("Reset this question? This permanently deletes the saved attempt, hint progress, and solved mark in this browser.")) return;
    localStorage.removeItem(progressKey(state.question));
    localStorage.removeItem(attemptKey(state.question));
    state.solved = readJson(SOLVED_KEY, {});
    delete state.solved[state.question.id];
    writeJson(SOLVED_KEY, state.solved);
    elements.attemptInput.value = "";
    elements.feedback.textContent = "Local attempt, hint progress, and solved mark were reset.";
    setProgress(state.question, 0);
    renderArchive();
    updateStats();
    updateSolvedButton();
  }

  function updateStats() {
    const records = Object.values(state.solved).filter(Boolean);
    elements.solvedCount.textContent = String(records.length);
    elements.streakCount.textContent = String(calculateStreak(records));
  }

  function calculateStreak(records) {
    const dates = new Set(records.map((record) => record.solveDate || record.date).filter(Boolean));
    let cursor = sydneyDateKey();
    if (!dates.has(cursor)) {
      cursor = shiftDateKey(cursor, -1);
    }
    let streak = 0;
    while (dates.has(cursor)) {
      streak += 1;
      cursor = shiftDateKey(cursor, -1);
    }
    return streak;
  }

  function shiftDateKey(dateKey, offset) {
    const date = new Date(`${dateKey}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + offset);
    return date.toISOString().slice(0, 10);
  }

  function renderArchive() {
    elements.archiveList.replaceChildren();
    const fragment = document.createDocumentFragment();
    for (const question of state.archive.slice(0, 12)) {
      const row = document.createElement("div");
      row.className = "archive-item";
      row.dataset.active = String(state.question && question.id === state.question.id);

      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${question.date} · ${question.topic || "Extension 2"}`;
      button.addEventListener("click", () => renderQuestion(question));

      const status = document.createElement("span");
      status.className = "archive-state";
      status.textContent = solvedRecordFor(question) ? "Solved" : "Open";

      row.append(button, status);
      fragment.appendChild(row);
    }
    elements.archiveList.appendChild(fragment);
  }

  async function loadArchive() {
    const todayKey = sydneyDateKey();
    elements.todayLabel.textContent = sydneyLongDate(todayKey);
    try {
      const response = await fetch(ARCHIVE_URL);
      if (!response.ok) throw new Error(`Archive returned ${response.status}`);
      const payload = await response.json();
      state.archive = normaliseQuestions(payload);
      if (!state.archive.length) throw new Error("Archive is empty");
      renderQuestion(chooseQuestion(state.archive));
    } catch (error) {
      elements.loadingState.hidden = true;
      elements.questionContent.hidden = true;
      elements.errorState.hidden = false;
      elements.appLoading.hidden = true;
      console.error(error);
    }
  }

  elements.saveAttemptButton.addEventListener("click", saveAttempt);
  elements.markSolvedButton.addEventListener("click", markSolved);
  elements.resetProgressButton.addEventListener("click", resetProgress);
  elements.retryButton.addEventListener("click", () => window.location.reload());
  elements.nextHintButton.addEventListener("click", () => {
    if (!state.question || state.progress >= 4) return;
    setProgress(state.question, state.progress + 1);
  });
  elements.attemptInput.addEventListener("input", () => {
    if (!state.question) return;
    localStorage.setItem(attemptKey(state.question), elements.attemptInput.value);
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== SOLVED_KEY) return;
    state.solved = readJson(SOLVED_KEY, {});
    renderArchive();
    updateStats();
    updateSolvedButton();
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }

  loadArchive();
})();
