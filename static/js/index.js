// (openModal, closeModal, subjectCount, updateSliderValue, addSubject, removeSubject, submitTimetableUrl, populateSubjectsFromTimetable 함수는 기존과 거의 동일하게 유지)
// submitTimetableUrl 함수 내부에서 성공 시 timetable_slots 필드를 채우고 populateSubjectsFromTimetable 호출하는 부분은 중요합니다.

function openModal() {
    document.getElementById('overlay').style.display = 'block';
    document.getElementById('modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('overlay').style.display = 'none';
    document.getElementById('modal').style.display = 'none';
    document.getElementById('new_url').value = '';
}

// static/js/index.js

// ... (openModal, closeModal functions remain the same) ...
let subjectCount = 0;

document.addEventListener('DOMContentLoaded', function() {
    const initialTimetableJson = document.getElementById('timetable_slots').value;
    const initialSubjectsJson = document.getElementById('initial_subjects_data_script_tag')?.textContent || '[]'; // Get from script tag

    let initialTimetableSlots = [];
    try {
        if (initialTimetableJson) {
            initialTimetableSlots = JSON.parse(initialTimetableJson);
        }
    } catch (e) {
        console.error('Error parsing initial timetable JSON:', e);
    }

    let initialSubjectsData = [];
    try {
        // The initial_subjects_data is now passed directly as a JSON string
        // Make sure it's properly escaped if rendered into a script tag, or use a hidden input.
        // For simplicity, let's assume it's available if Flask passes it.
        // We'll use the 'initial_subjects_data_script_tag' approach.
        initialSubjectsData = JSON.parse(initialSubjectsJson);
    } catch (e) {
        console.error('Error parsing initial subjects JSON:', e);
    }


    if (initialSubjectsData && initialSubjectsData.length > 0) {
        populateSubjectsFromSavedSubjects(initialSubjectsData);
        console.log('페이지 로드: 저장된 과목 데이터로 목록을 채웠습니다.');
    } else if (initialTimetableSlots && initialTimetableSlots.length > 0) {
        // If no saved subjects, but timetable exists (e.g., after Everytime load without planning)
        populateSubjectsFromTimetable(initialTimetableSlots);
        console.log('페이지 로드: 시간표 데이터로 과목 목록을 채웠습니다 (저장된 과목 없음).');
    } else if (document.querySelectorAll('#subjects .subject-item').length === 0) {
        addSubject(null); // Add one blank subject if nothing else is loaded
        console.log('페이지 로드: 초기 과목 입력 필드를 추가합니다.');
    }


    const loadJsonButton = document.getElementById('loadJsonBtn');
    if (loadJsonButton) {
        loadJsonButton.addEventListener('click', loadTimetableFromJson);
    }

    const planForm = document.getElementById('planForm');
    if (planForm) {
        planForm.addEventListener('submit', function(e) {
            // This part collects subject data and puts it into a hidden field 'subjects_json'
            // This is crucial for the backend to receive the correct subject details.
            const oldSubjectsInput = document.getElementById('subjects_json_hidden_input');
            if (oldSubjectsInput) oldSubjectsInput.remove();

            const subjectItems = document.querySelectorAll('.subject-item');
            const subjectsArr = [];
            subjectItems.forEach(item => {
                const nameInput = item.querySelector('input[name="name"]');
                const weightInput = item.querySelector('input[name="weight"]');
                const majorCheckbox = item.querySelector('input[name="major"]');

                const name = nameInput ? nameInput.value.trim() : "";
                const weight = weightInput ? weightInput.value : "50"; // default if somehow missing
                const major = majorCheckbox ? majorCheckbox.checked : false; // default if somehow missing

                if (name) {
                    subjectsArr.push({ name, weight: Number(weight), major });
                }
            });

            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'subjects_json'; // This name is what app.py /plan POST expects
            input.id = 'subjects_json_hidden_input';
            input.value = JSON.stringify(subjectsArr);
            planForm.appendChild(input);
        });
    }
});


function populateSubjectsFromTimetable(slots) {
    const subjectsDiv = document.getElementById('subjects');
    subjectsDiv.innerHTML = '';
    subjectCount = 0;

    const uniqueSubjects = new Set();
    if (Array.isArray(slots)) {
        slots.forEach(slot => {
            if (slot && slot.length > 1 && slot[0] === '수업' && typeof slot[1] === 'string' && slot[1].trim()) {
                uniqueSubjects.add(slot[1].trim());
            }
        });
    }

    if (uniqueSubjects.size > 0) {
        uniqueSubjects.forEach(subjectName => {
            addSubject(null, subjectName, '50', false); // Default weight 50, not major
        });
    } else {
        addSubject(null); // Add one blank if no subjects in timetable
    }
}

function updateSliderValue(spanId, value) {
    const spanElement = document.getElementById(spanId);
    if (spanElement) {
        spanElement.innerText = value;
    }
}

function addSubject(afterElement, subjectName = '', initialWeight = '50', isMajor = false) {
    subjectCount++;
    const subjectItemId = `subjectItem${subjectCount}`;
    const nameId = `name${subjectCount}`;
    const majorId = `major${subjectCount}`;
    const weightId = `weight${subjectCount}`;
    const sliderValueId = `sliderValue${subjectCount}`;

    const div = document.createElement('div');
    div.classList.add('subject-item');
    div.id = subjectItemId;

    // Ensure initialWeight is a string for the value attribute
    const weightStr = String(initialWeight);
    // Ensure isMajor is a boolean for the checked property
    const majorChecked = Boolean(isMajor);

    div.innerHTML = `
    <div class="subject-inputs">
      <label for="${nameId}">Subject:</label>
      <input type="text" id="${nameId}" name="name" value="${subjectName}" required>

      <div class="form-group major-course-group">
        <label for="${majorId}" class="major-course-label">Major Subject:</label>
        <input type="checkbox" id="${majorId}" name="major" class="toggle-btn" ${majorChecked ? 'checked' : ''}>
      </div>

      <div class="form-group importance-level-group">
        <label for="${weightId}" class="importance-label">Importance:</label>
        <span id="${sliderValueId}" class="slider-value-display">${weightStr}</span>
      </div>
      <input type="range" id="${weightId}" name="weight" min="0" max="100" step="1" value="${weightStr}"
             class="importance-slider"
             oninput="updateSliderValue('${sliderValueId}', this.value)">
    </div>
    <div class="subject-actions-container">
      <div class="action-left">
        <button type="button" class="plus-style-button action-btn remove-btn" onclick="removeSubject('${subjectItemId}')">🗑️ Delete</button>
      </div>
      <div class="action-right">
        <button type="button" class="plus-style-button action-btn add-below-btn" onclick="addSubject(this.closest('.subject-item'))"><span class="icon">+</span> Add Subject</button>
      </div>
    </div>
  `;

    const subjectsDiv = document.getElementById('subjects');
    if (afterElement) {
        afterElement.parentNode.insertBefore(div, afterElement.nextSibling);
    } else {
        subjectsDiv.appendChild(div);
    }
    // Ensure slider value is correctly displayed if it's not the default
    updateSliderValue(sliderValueId, weightStr);
}

function removeSubject(subjectItemId) {
    const subjectItemToRemove = document.getElementById(subjectItemId);
    const subjectsDiv = document.getElementById('subjects');
    if (!subjectItemToRemove) return;
    if (subjectsDiv.getElementsByClassName('subject-item').length > 1) {
        subjectItemToRemove.remove();
    } else {
        alert('At least one subject must remain.');
    }
}

function submitTimetableUrl() {
    const timetableUrl = document.getElementById('new_url').value;
    if (!timetableUrl) {
        alert('URL을 입력해주세요.');
        return;
    }
    const formData = new FormData();
    formData.append('new_url', timetableUrl);

    fetch('/process_timetable', {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errData => {
                    throw new Error(errData.error || `서버 오류: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                alert('시간표 로딩 오류: ' + data.error);
            } else if (Array.isArray(data.timetable_slots)) {
                document.getElementById('timetable_slots').value = JSON.stringify(data.timetable_slots);
                // When timetable is loaded from Everytime, `data.subjects` from /process_timetable
                // is in the format: [{"name": "OS", "professor": "...", "info": [...]}, ...].
                // We should use populateSubjectsFromTimetable which extracts names and sets default weights/majors.
                populateSubjectsFromTimetable(data.timetable_slots);
                closeModal();
                alert(data.message || '시간표를 성공적으로 불러왔습니다! (Everytime)');
            } else {
                alert('시간표 데이터를 불러오지 못했거나, 형식이 올바르지 않습니다. (Everytime)');
            }
        })
        .catch(error => {
            console.error('Everytime 시간표 처리 중 오류 발생:', error);
            alert('Everytime 시간표 처리 중 오류가 발생했습니다: ' + error.message);
        });
}

function loadTimetableFromJson() {
    fetch('/load_stored_timetable', {
        method: 'GET'
    })
        .then(response => {
            if (!response.ok) {
                if (response.status === 404) {
                    return response.json().then(data => {
                        alert(data.message || '저장된 시간표 데이터가 없습니다.');
                        // If no data, ensure at least one blank subject input remains or is added
                        const subjectsDiv = document.getElementById('subjects');
                        if (subjectsDiv.children.length === 0) addSubject(null);
                        throw new Error('No stored timetable found.');
                    });
                }
                throw new Error(`서버 응답 오류: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                alert('저장된 시간표 로딩 오류: ' + data.error);
            } else if (Array.isArray(data.timetable_slots)) {
                document.getElementById('timetable_slots').value = JSON.stringify(data.timetable_slots);
                // `data.subjects` from /load_stored_timetable should be in the format
                // [{"name": "OS", "weight": 70, "major": true/1.0}, ...]
                // if it was saved by the /plan route.
                if (Array.isArray(data.subjects) && data.subjects.length > 0 && data.subjects[0].hasOwnProperty('weight')) {
                    populateSubjectsFromSavedSubjects(data.subjects);
                } else if (Array.isArray(data.timetable_slots)) { // Fallback if subjects aren't in the new format
                    populateSubjectsFromTimetable(data.timetable_slots);
                } else {
                    // Ensure at least one subject item if all else fails
                    const subjectsDiv = document.getElementById('subjects');
                    subjectsDiv.innerHTML = '';
                    subjectCount = 0;
                    addSubject(null);
                }
                alert(data.message || '저장된 시간표를 성공적으로 불러왔습니다!');
            } else {
                alert('저장된 시간표 데이터를 불러오지 못했거나, 형식이 올바르지 않습니다.');
            }
        })
        .catch(error => {
            console.error('저장된 시간표 로딩 중 오류 발생:', error.message);
            // Alert is often handled by the response checks, so only alert if not already handled.
            if (error.message !== 'No stored timetable found.') {
                // alert('저장된 시간표 로딩 중 오류가 발생했습니다: ' + error.message);
            }
        });
}

function populateSubjectsFromSavedSubjects(subjects) {
    const subjectsDiv = document.getElementById('subjects');
    subjectsDiv.innerHTML = '';
    subjectCount = 0;
    if (Array.isArray(subjects) && subjects.length > 0) {
        subjects.forEach(subj => {
            // `subj.major` will be 1.0 or 0.0 if saved from /plan. Boolean() converts these correctly.
            // `subj.weight` will be a number.
            addSubject(
                null,
                subj.name || '',
                subj.weight !== undefined ? String(subj.weight) : '50',
                subj.major !== undefined ? Boolean(subj.major) : false // Handles 1.0/0.0 from JSON
            );
        });
    } else {
        addSubject(null); // Add one blank if no subjects
    }
}