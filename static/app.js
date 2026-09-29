const uploadForm = document.getElementById('uploadForm');
const pdfFile = document.getElementById('pdfFile');
const statusEl = document.getElementById('status');
const uploadPanel = document.getElementById('uploadPanel');
const workspace = document.getElementById('workspace');
const pagesEl = document.getElementById('pages');
const topicList = document.getElementById('topicList');
const reactionPanel = document.getElementById('reactionPanel');
const modeSwitch = document.getElementById('modeSwitch');
const filenameEl = document.getElementById('filename');
const matchSummary = document.getElementById('matchSummary');

let currentDoc = null;
let currentMode = 'Abi';
let selectedTopic = null;
let currentUtterance = null;

const analysisProgress = document.getElementById('analysisProgress');
const progressStage = document.getElementById('progressStage');
const progressDetail = document.getElementById('progressDetail');
const progressPercent = document.getElementById('progressPercent');
const progressBar = document.getElementById('progressBar');
const progressTrack = analysisProgress.querySelector('.progress-track');
const reactionCounter = document.getElementById('reactionCounter');
const elapsedTime = document.getElementById('elapsedTime');
const analyzeButton = uploadForm.querySelector('button[type="submit"]');

let analysisStartedAt = null;
let elapsedTimer = null;

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const mins = Math.floor(total / 60);
  const secs = String(total % 60).padStart(2, '0');
  return `${mins}:${secs}`;
}

function startProgressUI() {
  analysisStartedAt = Date.now();
  analysisProgress.hidden = false;
  analysisProgress.classList.remove('progress-error', 'progress-complete');
  statusEl.textContent = '';
  analyzeButton.disabled = true;
  analyzeButton.textContent = 'Analyzing…';
  updateProgressUI({
    progress: 1,
    stage: 'Uploading syllabus',
    detail: 'Sending the PDF to the analyzer',
    reactions_completed: 0,
    reactions_total: 0,
  });
  clearInterval(elapsedTimer);
  elapsedTimer = setInterval(() => {
    elapsedTime.textContent = `${formatElapsed(Date.now() - analysisStartedAt)} elapsed`;
  }, 1000);
}

function stopProgressTimer() {
  clearInterval(elapsedTimer);
  elapsedTimer = null;
  if (analysisStartedAt) {
    elapsedTime.textContent = `${formatElapsed(Date.now() - analysisStartedAt)} elapsed`;
  }
}

function updateProgressUI(job) {
  const pct = Math.max(0, Math.min(100, Number(job.progress ?? 0)));
  progressBar.style.width = `${pct}%`;
  progressPercent.textContent = `${Math.round(pct)}%`;
  progressTrack.setAttribute('aria-valuenow', String(Math.round(pct)));
  progressStage.textContent = job.stage || 'Analyzing syllabus';
  progressDetail.textContent = job.detail || 'Working…';

  const done = Number(job.reactions_completed || 0);
  const total = Number(job.reactions_total || 0);
  if (total > 0) {
    reactionCounter.textContent = `${done} / ${total} student reactions complete`;
  } else if (pct < 32) {
    reactionCounter.textContent = 'Reading and mapping the PDF';
  } else {
    reactionCounter.textContent = 'Preparing student simulation';
  }
}

async function pollAnalysisJob(jobId) {
  while (true) {
    const res = await fetch(`/api/job/${jobId}`, { cache: 'no-store' });
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || 'Could not read analysis progress');

    updateProgressUI(job);

    if (job.status === 'error') {
      analysisProgress.classList.add('progress-error');
      stopProgressTimer();
      throw new Error(job.error || job.detail || 'Analysis failed');
    }

    if (job.status === 'complete') {
      analysisProgress.classList.add('progress-complete');
      stopProgressTimer();
      await new Promise(resolve => setTimeout(resolve, 350));
      const docRes = await fetch(`/api/document/${job.document_id}`);
      const doc = await docRes.json();
      if (!docRes.ok) throw new Error(doc.detail || 'Could not load analysis results');
      return doc;
    }

    await new Promise(resolve => setTimeout(resolve, 700));
  }
}

uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = pdfFile.files[0];
  if (!file) return;

  startProgressUI();
  const data = new FormData();
  data.append('file', file);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: data });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || 'Upload failed');

    currentDoc = await pollAnalysisJob(body.job_id);
    renderDocument();
  } catch (err) {
    stopProgressTimer();
    analysisProgress.classList.add('progress-error');
    progressStage.textContent = 'Analysis could not finish';
    progressDetail.textContent = err.message;
    statusEl.textContent = err.message;
    analyzeButton.disabled = false;
    analyzeButton.textContent = 'Analyze syllabus';
  }
});


modeSwitch.addEventListener('click', (e) => {
  if (!e.target.matches('button')) return;
  currentMode = e.target.dataset.mode;
  modeSwitch.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === e.target));
  refreshMarkers();
  if (selectedTopic) showReaction(selectedTopic);
});

function renderDocument() {
  analyzeButton.disabled = false;
  analyzeButton.textContent = 'Analyze syllabus';
  uploadPanel.hidden = true;
  workspace.hidden = false;
  modeSwitch.hidden = false;
  filenameEl.textContent = currentDoc.filename;
  matchSummary.textContent = `${currentDoc.topics.length} concepts anchored · ${currentDoc.agent_mode} agents`;
  pagesEl.innerHTML = '';
  topicList.innerHTML = '';

  for (let i = 0; i < currentDoc.page_count; i++) {
    const wrap = document.createElement('div');
    wrap.className = 'page-wrap';
    wrap.dataset.page = i;

    const img = document.createElement('img');
    img.src = `/rendered/${currentDoc.document_id}/${i + 1}.png`;
    img.className = 'page-image';
    img.addEventListener('load', refreshMarkers);

    const overlay = document.createElement('div');
    overlay.className = 'page-overlay';

    wrap.append(img, overlay);
    pagesEl.appendChild(wrap);
  }

  currentDoc.topics.forEach((topic, idx) => {
    const item = document.createElement('button');
    item.className = 'topic-item';
    item.innerHTML = `<span class="topic-num">${idx + 1}</span><span><strong>${escapeHtml(topic.topic_label)}</strong><small>Page ${topic.page + 1} · match ${Math.round(topic.confidence * 100)}%</small></span>`;
    item.addEventListener('click', () => focusTopic(topic));
    topicList.appendChild(item);
  });

  setTimeout(refreshMarkers, 100);
}

function getAgentIcon(name) {
  if (name === 'Abi') {
    return '👩‍💻';
  }

  if (name === 'Tim') {
    return '🧑‍💻';
  }

  return '👥';
}

function refreshMarkers() {
  if (!currentDoc) return;

  document
    .querySelectorAll('.page-overlay')
    .forEach(el => {
      el.innerHTML = '';
    });

  for (let pageIndex = 0; pageIndex < currentDoc.page_count; pageIndex++) {
    const pageWrap = document.querySelector(
      `.page-wrap[data-page="${pageIndex}"]`
    );

    if (!pageWrap) continue;

    const img = pageWrap.querySelector('.page-image');
    const overlay = pageWrap.querySelector('.page-overlay');

    if (!img || !overlay) continue;
    if (!img.complete || !img.naturalWidth) continue;

    const rect = img.getBoundingClientRect();

    const displayW = rect.width;
    const displayH = rect.height;

    if (!displayW || !displayH) continue;

    const [pdfW, pdfH] = currentDoc.page_sizes[pageIndex];

    const sx = displayW / pdfW;
    const sy = displayH / pdfH;

    const pageTopics = currentDoc.topics
      .filter(topic => topic.page === pageIndex)
      .map(topic => {
        const [x0, y0, x1, y1] = topic.bbox;

        return {
          topic,
          box: {
            x0: x0 * sx,
            y0: y0 * sy,
            x1: x1 * sx,
            y1: y1 * sy
          }
        };
      });

    const clusters = clusterOverlappingAnchors(pageTopics);

    clusters.forEach(cluster => {
      const union = getUnionBox(
        cluster.map(item => item.box)
      );

      const topics = cluster.map(item => item.topic);

      const highlight = document.createElement('button');

      highlight.className = 'anchor-highlight';

      highlight.style.left = `${union.x0}px`;
      highlight.style.top = `${union.y0}px`;
      highlight.style.width =
        `${Math.max(24, union.x1 - union.x0)}px`;
      highlight.style.height =
        `${Math.max(18, union.y1 - union.y0)}px`;

      if (topics.length === 1) {
        highlight.title = topics[0].topic_label;

        highlight.addEventListener(
          'click',
          () => showReaction(topics[0])
        );
      } else {
        highlight.title =
          `${topics.length} concepts share this passage`;

        highlight.style.borderStyle = 'dashed';

        highlight.addEventListener(
          'click',
          () => openAnchorCluster(topics)
        );
      }

      overlay.appendChild(highlight);

      const marker = document.createElement('button');

      marker.className =
        `reaction-marker mode-${currentMode.toLowerCase()}`;

      marker.style.left =
        `${Math.max(6, displayW - 42)}px`;

      marker.style.top =
        `${Math.max(
          4,
          Math.min(
            displayH - 38,
            union.y0
          )
        )}px`;

      const symbol =
        currentMode === 'Compare'
          ? '👥'
          : getAgentIcon(currentMode);

      if (topics.length > 1) {
        marker.innerHTML = `
          <span class="marker-symbol">${symbol}</span>
          <sup class="marker-count">${topics.length}</sup>
        `;
      } else {
        marker.innerHTML = `
          <span class="marker-symbol">${symbol}</span>
        `;
      }

      marker.title =
        topics.length > 1
          ? `${topics.length} concepts share this passage — ${currentMode}`
          : `${topics[0].topic_label} — ${currentMode}`;

      marker.setAttribute(
        'aria-label',
        marker.title
      );

      marker.addEventListener(
        'click',
        () => {
          if (topics.length === 1) {
            showReaction(topics[0]);
          } else {
            openAnchorCluster(topics);
          }
        }
      );

      overlay.appendChild(marker);
    });
  }
}

function clusterOverlappingAnchors(items) {
  const clusters = [];

  for (const item of items) {
    const matchingIndexes = [];

    for (let i = 0; i < clusters.length; i++) {
      if (
        clusters[i].some(existing =>
          anchorsOverlap(
            existing.box,
            item.box
          )
        )
      ) {
        matchingIndexes.push(i);
      }
    }

    if (matchingIndexes.length === 0) {
      clusters.push([item]);
      continue;
    }

    const merged = [item];

    // Merge all clusters touched by this anchor.
    for (
      let i = matchingIndexes.length - 1;
      i >= 0;
      i--
    ) {
      merged.push(
        ...clusters.splice(
          matchingIndexes[i],
          1
        )[0]
      );
    }

    clusters.push(merged);
  }

  return clusters;
}

function openAnchorCluster(topics) {
  selectedTopic = null;

  reactionPanel.innerHTML = `
    <div class="panel-kicker">
      Overlapping annotations
    </div>

    <h2>
      ${topics.length} concepts share this passage
    </h2>

    <p>
      Choose which reaction you want to view.
    </p>

    <div class="cluster-options">
      ${topics.map(topic => `
        <button
          class="cluster-option"
          data-topic-id="${escapeHtml(topic.topic_id)}"
        >
          <strong>
            ${escapeHtml(topic.topic_label)}
          </strong>

          <small>
            Match ${Math.round(topic.confidence * 100)}%
          </small>
        </button>
      `).join('')}
    </div>
  `;

  reactionPanel
    .querySelectorAll('.cluster-option')
    .forEach(btn => {
      btn.addEventListener('click', () => {
        const topic = topics.find(
          t => t.topic_id === btn.dataset.topicId
        );

        if (topic) {
          showReaction(topic);
        }
      });
    });
}

function anchorsOverlap(a, b) {
  const tolerance = 4;

  const ix0 = Math.max(
    a.x0 - tolerance,
    b.x0 - tolerance
  );

  const iy0 = Math.max(
    a.y0 - tolerance,
    b.y0 - tolerance
  );

  const ix1 = Math.min(
    a.x1 + tolerance,
    b.x1 + tolerance
  );

  const iy1 = Math.min(
    a.y1 + tolerance,
    b.y1 + tolerance
  );

  if (ix1 <= ix0 || iy1 <= iy0) {
    return false;
  }

  const intersectionArea =
    (ix1 - ix0) *
    (iy1 - iy0);

  const areaA = Math.max(
    1,
    (a.x1 - a.x0) *
      (a.y1 - a.y0)
  );

  const areaB = Math.max(
    1,
    (b.x1 - b.x0) *
      (b.y1 - b.y0)
  );

  // Merge when 15% or more of the smaller
  // highlight overlaps the other.
  return (
    intersectionArea /
      Math.min(areaA, areaB) >=
    0.15
  );
}


function getUnionBox(boxes) {
  return boxes.reduce(
    (acc, box) => ({
      x0: Math.min(acc.x0, box.x0),
      y0: Math.min(acc.y0, box.y0),
      x1: Math.max(acc.x1, box.x1),
      y1: Math.max(acc.y1, box.y1)
    }),
    {
      x0: Infinity,
      y0: Infinity,
      x1: -Infinity,
      y1: -Infinity
    }
  );
}



function focusTopic(topic) {
  const page = document.querySelector(`.page-wrap[data-page="${topic.page}"]`);
  page?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  showReaction(topic);
}

function showReaction(topic) {
  selectedTopic = topic;
  if (currentMode === 'Compare') {
    reactionPanel.innerHTML = `
      <div class="panel-kicker">${escapeHtml(topic.topic_label)}</div>
      <h2>Compare students</h2>
      <div class="compare-grid">
        ${studentCard('Abi', topic.evaluations.Abi)}
        ${studentCard('Tim', topic.evaluations.Tim)}
      </div>
      ${sourceCard(topic)}
    `;
  } else {
    const data = topic.evaluations[currentMode];
    reactionPanel.innerHTML = `
      <div class="student-header">
        <div class="avatar">
          ${getAgentIcon(currentMode)}
        </div>
        <div><div class="panel-kicker">${escapeHtml(topic.topic_label)}</div><h2>${currentMode}</h2></div>
      </div>
      ${reactionFields(currentMode, data)}
      ${sourceCard(topic)}
    `;
  }
}

function studentCard(name, data) {
  return `
    <section class="student-card">
      <div class="student-mini">
        <span class="avatar small">
            ${getAgentIcon(name)}
        </span>
        <strong>${name}</strong>
      </div>

      ${reactionFields(name, data)}
    </section>
  `;
}


// function reactionFields(data) {
//   return `
//     <div class="field">
//       <label>💭 Internal monologue</label>
//       <p>${escapeHtml(data.internal_monologue || '—')}</p>
//     </div>

//     <div class="field">
//       <label>⚠ Perceived concerns</label>
//       <p>${escapeHtml(data.perceived_concerns || '—')}</p>
//     </div>

//     <div class="field">
//       <label>🏷 Concern category</label>
//       <p>${escapeHtml(data.concern_category || '—')}</p>
//     </div>

//     <div class="field">
//       <label>🔥 Concern severity</label>
//       <div class="confidence-pill">
//         ${escapeHtml(data.concern_severity ?? '—')} / 5
//       </div>
//     </div>

//     <div class="field">
//       <label>📊 Confidence to succeed</label>
//       <div class="confidence-pill">
//         ${escapeHtml(data.confidence_to_succeed || '—')}
//       </div>
//     </div>

//     <div class="field">
//       <label>→ Immediate next step</label>
//       <p>${escapeHtml(data.immediate_next_step || '—')}</p>
//     </div>
//   `;
// }

function speakReaction(name, data) {
  if (!('speechSynthesis' in window)) {
    alert('Text-to-speech is not supported in this browser.');
    return;
  }

  const synth = window.speechSynthesis;

  // Stop anything currently speaking.
  synth.cancel();

  const parts = [
    `${name}'s reaction.`,

    data.internal_monologue || '',

    data.interpretation || '',

    data.questions_or_uncertainty || '',

    data.self_assessment || '',

    data.immediate_next_step || ''
  ].filter(Boolean);

  const text = parts.join(' ');

  // Keep a global reference to the utterance.
  currentUtterance =
    new SpeechSynthesisUtterance(text);

  currentUtterance.rate = 0.95;
  currentUtterance.pitch = 1.0;
  currentUtterance.volume = 1.0;

  currentUtterance.onstart = () => {
    console.log(
      `Started speaking ${name}'s reaction`
    );
  };

  currentUtterance.onend = () => {
    console.log(
      `Finished speaking ${name}'s reaction`
    );

    currentUtterance = null;
  };

  currentUtterance.onerror = event => {
    console.error(
      'Speech synthesis error:',
      event
    );

    currentUtterance = null;
  };

  /*
   * Some browsers need a short pause after cancel()
   * before another utterance can be started.
   */
  setTimeout(() => {
    if (synth.paused) {
      synth.resume();
    }

    synth.speak(
      currentUtterance
    );
  }, 100);
}

reactionPanel.addEventListener('click', (event) => {
  const button = event.target.closest('.speak-reaction-btn');

  if (!button) return;
  if (!selectedTopic) return;

  const studentName = button.dataset.student;

  const data =
    selectedTopic.evaluations?.[studentName];

  if (!data) {
    console.error(
      `No reaction data found for ${studentName}`
    );
    return;
  }

  speakReaction(
    studentName,
    data
  );
});


// function reactionFields(data) {
//   return `
//     <div class="field">
//       <label>💭 Internal monologue</label>
//       <p>${escapeHtml(data.internal_monologue || '—')}</p>
//     </div>

//     <div class="field">
//       <label>🧭 Interpretation</label>
//       <p>${escapeHtml(data.interpretation || '—')}</p>
//     </div>

//     <div class="field">
//       <label>❓ Questions or uncertainty</label>
//       <p>${escapeHtml(data.questions_or_uncertainty || 'None')}</p>
//     </div>

//     <div class="field">
//       <label>→ Immediate next step</label>
//       <p>${escapeHtml(data.immediate_next_step || '—')}</p>
//     </div>

//     <div class="field">
//       <label>📈 Self-assessment</label>
//       <p>${escapeHtml(data.self_assessment || 'No change')}</p>
//     </div>
//   `;
// }

function reactionFields(name, data) {
  return `
    <div class="field">
      <label>💭 Internal monologue</label>
      <p>${escapeHtml(data.internal_monologue || '—')}</p>
    </div>

    <div class="field">
      <label>🧭 Interpretation</label>
      <p>${escapeHtml(data.interpretation || '—')}</p>
    </div>

    <div class="field">
      <label>❓ Questions or uncertainty</label>
      <p>${escapeHtml(data.questions_or_uncertainty || 'None')}</p>
    </div>

    <div class="field">
      <label>📈 Self-assessment</label>
      <p>${escapeHtml(data.self_assessment || 'No change')}</p>
    </div>

    <div class="field">
      <label>→ Immediate next step</label>
      <p>${escapeHtml(data.immediate_next_step || '—')}</p>
    </div>

    <div class="field">
      <button
        type="button"
        class="speak-reaction-btn"
        data-student="${escapeHtml(name)}"
      >
        🔊 Hear ${escapeHtml(name)}'s reaction
      </button>
    </div>
  `;
}

let resizeTimer = null;

window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);

  resizeTimer = setTimeout(() => {
    requestAnimationFrame(() => {
      refreshMarkers();
    });
  }, 200);
});

document.addEventListener('load', event => {
  if (
    event.target &&
    event.target.classList &&
    event.target.classList.contains('page-image')
  ) {
    requestAnimationFrame(() => {
      refreshMarkers();
    });
  }
}, true);


function sourceCard(topic) {
  return `<details class="source-card"><summary>Why is this reaction placed here?</summary><p><strong>Matched text:</strong> ${escapeHtml(topic.anchor_text)}</p><p><strong>Anchor confidence:</strong> ${Math.round(topic.confidence * 100)}%</p><p class="muted">Placement metadata is separate from the agent's structured output.</p></details>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[c]));
}
