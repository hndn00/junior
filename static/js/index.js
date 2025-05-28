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

let subjectCount = 0;

document.addEventListener('DOMContentLoaded', function() {
    // 페이지 로드 시, Flask 템플릿으로부터 timetable_slots 필드에 값이 주입된 경우를 처리했었으나,
    // 이제 app.py의 /plan GET 요청은 항상 빈 timetable_slots를 전달하므로,
    // initialTimetableData는 항상 빈 문자열이 됩니다.
    const initialTimetableData = document.getElementById('timetable_slots').value;

    // initialTimetableData가 비어있으므로, 항상 아래 else if 조건 또는 그 다음 else 조건으로 빠지게 됩니다.
    // 결과적으로 페이지 로드 시에는 항상 과목 목록이 초기화되고 하나의 빈 과목 입력칸이 생성됩니다.
    if (initialTimetableData) {
        // 이 블록은 사실상 실행되지 않음 (app.py 변경으로 인해)
        try {
            const timetableSlots = JSON.parse(initialTimetableData);
            if (Array.isArray(timetableSlots) && timetableSlots.length > 0) {
                populateSubjectsFromTimetable(timetableSlots);
                console.log('Flask에서 전달된 초기 시간표 데이터로 과목 목록을 채웠습니다. (이 메시지는 이제 나타나지 않아야 합니다)');
            } else if (document.querySelectorAll('#subjects .subject-item').length === 0) {
                addSubject(null);
            }
        } catch (e) {
            console.error('초기 시간표 데이터 파싱 오류 (이 오류는 이제 발생하지 않아야 합니다):', e);
            if (document.querySelectorAll('#subjects .subject-item').length === 0) {
                addSubject(null);
            }
        }
    } else if (document.querySelectorAll('#subjects .subject-item').length === 0) {
        // timetable_slots hidden input이 비어있고, 현재 화면에 과목 아이템도 없으면 초기 아이템 추가
        addSubject(null);
        console.log('페이지 로드: 초기 과목 입력 필드를 추가합니다.');
    } else {
        // timetable_slots hidden input이 비어있지만, 화면에 이미 과목 아이템이 있는 경우 (예: 브라우저 뒤로가기 캐시)
        // 이 경우는 일반적으로 발생하지 않거나, 발생하더라도 사용자가 새로고침하면 초기화됨.
        // 명시적으로 초기화하고 싶다면 여기서 subjectsDiv.innerHTML = ''; 후 addSubject(null); 호출.
        // 하지만 일반적으로는 위의 else if 조건으로 충분합니다.
        console.log('페이지 로드: timetable_slots는 비어있으나, 기존 과목 아이템이 존재합니다. (브라우저 캐시 가능성)');
    }

    // "Load JSON" 버튼 이벤트 리스너 추가 (이전과 동일)
    const loadJsonButton = document.getElementById('loadJsonBtn');
    if (loadJsonButton) {
        loadJsonButton.addEventListener('click', loadTimetableFromJson);
    }

    // 폼 제출 이벤트 처리 (최종 subject 정보를 hidden input에 추가)
    const planForm = document.getElementById('planForm');
    if (planForm) {
        planForm.addEventListener('submit', function(e) {
            // 기존에 추가된 hidden input 제거
            const oldSubjectsInput = document.getElementById('subjects_json');
            if (oldSubjectsInput) oldSubjectsInput.remove();

            // 현재 화면의 subject 정보를 모두 수집
            const subjectItems = document.querySelectorAll('.subject-item');
            const subjectsArr = [];
            subjectItems.forEach(item => {
                const name = item.querySelector('input[name="name"]').value.trim();
                const weight = item.querySelector('input[name="weight"]').value;
                const major = item.querySelector('input[name="major"]').checked;
                if (name) {
                    subjectsArr.push({ name, weight: Number(weight), major });
                }
            });

            // hidden input으로 추가
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'subjects_json';
            input.id = 'subjects_json';
            input.value = JSON.stringify(subjectsArr);
            planForm.appendChild(input);
        });
    }
});

// ... (다른 함수들은 이전 답변과 동일하게 유지) ...
// populateSubjectsFromTimetable 함수는 slots가 비어있을 때 addSubject(null)을 호출하도록 되어 있으므로,
// 빈 timetable_slots가 전달되면 자동으로 하나의 과목 입력칸을 생성합니다.

function populateSubjectsFromTimetable(slots) {
    const subjectsDiv = document.getElementById('subjects');
    subjectsDiv.innerHTML = ''; // 기존 과목 목록 비우기
    subjectCount = 0; // 과목 카운트 초기화

    const uniqueSubjects = new Set();
    if (Array.isArray(slots)) {
        slots.forEach(slot => {
            if (slot && slot.length > 1 && slot[0] === '수업'
                && typeof slot[1] === 'string' && slot[1].trim()) {
                uniqueSubjects.add(slot[1].trim());
            }
        });
    }

    if (uniqueSubjects.size > 0) {
        uniqueSubjects.forEach(subjectName => {
            addSubject(null, subjectName);
        });
    } else {
        // 불러온 시간표에 수업 과목이 없거나, 아예 빈 시간표인 경우 (또는 초기 로드 시)
        addSubject(null);
        console.log('시간표에 수업 정보가 없거나 빈 시간표입니다. 기본 과목 입력 필드를 추가합니다.');
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
    const nameId        = `name${subjectCount}`;
    const majorId       = `major${subjectCount}`;
    const weightId      = `weight${subjectCount}`;
    const sliderValueId = `sliderValue${subjectCount}`; //

    const div = document.createElement('div');
    div.classList.add('subject-item');
    div.id = subjectItemId;

    div.innerHTML = `
    <div class="subject-inputs">
      <label for="${nameId}">Subject:</label>
      <input type="text" id="${nameId}" name="name" value="${subjectName}" required>

      <div class="form-group major-course-group">
        <label for="${majorId}" class="major-course-label">Major Subject:</label>
        <input type="checkbox" id="${majorId}" name="major" class="toggle-btn" ${isMajor ? 'checked' : ''}>
      </div>

      <div class="form-group importance-level-group">
        <label for="${weightId}" class="importance-label">Importance:</label>
        <span id="${sliderValueId}" class="slider-value-display">${initialWeight}</span>
      </div>
      <input type="range" id="${weightId}" name="weight" min="0" max="100" step="1" value="${initialWeight}"
             class="importance-slider"
             oninput="updateSliderValue('${sliderValueId}', this.value)">
    </div>
    <div class="subject-actions-container">
      <div class="action-left">
        <button type="button" class="remove-btn" onclick="removeSubject('${subjectItemId}')">🗑️ Delete</button>
      </div>
      <div class="action-right">
        <button type="button" class="add-below-btn" onclick="addSubject(this.closest('.subject-item'))">+ Add Subject</button>
      </div>
    </div>
  `; //

    const subjectsDiv = document.getElementById('subjects');
    if (afterElement) {
        afterElement.parentNode.insertBefore(div, afterElement.nextSibling);
    } else {
        subjectsDiv.appendChild(div);
    }
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

    fetch('/process_timetable', { // 이 URL은 app.py의 라우트와 일치해야 합니다.
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errData => {
                    throw new Error(errData.error || `서버 오류: ${response.status}`);
                }).catch(() => {
                    throw new Error(`서버 응답 오류: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Everytime 시간표 서버 응답:', data);
            if (data.error) {
                alert('시간표 로딩 오류: ' + data.error);
            }
            else if (Array.isArray(data.timetable_slots)) {
                document.getElementById('timetable_slots').value = JSON.stringify(data.timetable_slots);

                const totalHoursInput = document.getElementById('total_hours'); // total_hours 필드가 있다면
                if (totalHoursInput && data.total_hours) { // total_hours가 데이터에 포함되어 있다면
                    totalHoursInput.value = data.total_hours;
                }

                populateSubjectsFromTimetable(data.timetable_slots);
                closeModal();

                if (data.timetable_slots.length > 0) {
                    alert('시간표를 성공적으로 불러왔습니다! (Everytime)');
                } else if (data.message) {
                    alert(data.message);
                } else {
                    alert('시간표는 불러왔으나, 포함된 과목이 없습니다. (Everytime)');
                }
            }
            else {
                alert('시간표 데이터를 불러오지 못했거나, 형식이 올바르지 않습니다. (Everytime)');
            }
        })
        .catch(error => {
            console.error('Everytime 시간표 처리 중 오류 발생:', error);
            alert('Everytime 시간표 처리 중 오류가 발생했습니다: ' + error.message);
        });
}

// "Load JSON" 버튼 클릭 시 호출될 함수
function loadTimetableFromJson() {
    fetch('/load_stored_timetable', { // app.py 에 새로 추가한 라우트
        method: 'GET'
    })
        .then(response => {
            if (!response.ok) {
                // 404 (파일 없음) 등의 경우를 여기서 처리 가능
                if (response.status === 404) {
                    return response.json().then(data => {
                        alert(data.message || '저장된 시간표 데이터가 없습니다.');
                        throw new Error('No stored timetable found or failed to load.');
                    });
                }
                throw new Error(`서버 응답 오류: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('저장된 JSON 시간표 서버 응답:', data);
            if (data.error) { // app.py에서 error를 반환하는 경우가 있는지 확인 필요 (현재는 message 사용)
                alert('저장된 시간표 로딩 오류: ' + data.error);
            } else if (Array.isArray(data.timetable_slots)) {
                document.getElementById('timetable_slots').value = JSON.stringify(data.timetable_slots);
                // subjects도 있으면 반영
                if (Array.isArray(data.subjects) && data.subjects.length > 0) {
                    populateSubjectsFromSavedSubjects(data.subjects);
                } else {
                    populateSubjectsFromTimetable(data.timetable_slots);
                }
                alert(data.message || '저장된 시간표를 성공적으로 불러왔습니다!');
            } else {
                // 응답 형식이 예상과 다를 경우
                alert('저장된 시간표 데이터를 불러오지 못했거나, 형식이 올바르지 않습니다.');
            }
        })
        .catch(error => {
            console.error('저장된 시간표 로딩 중 오류 발생:', error);
            // alert('저장된 시간표 로딩 중 오류가 발생했습니다: ' + error.message); // 위에서 이미 alert 처리됨
        });
}

// 저장된 subjects 배열로 과목 입력 필드 채우기
function populateSubjectsFromSavedSubjects(subjects) {
    const subjectsDiv = document.getElementById('subjects');
    subjectsDiv.innerHTML = '';
    subjectCount = 0;
    if (Array.isArray(subjects) && subjects.length > 0) {
        subjects.forEach(subj => {
            addSubject(
                null,
                subj.name || '',
                subj.weight !== undefined ? String(subj.weight) : '50',
                subj.major === true
            );
        });
    } else {
        addSubject(null);
    }
}

function populateSubjectsFromTimetable(slots) {
    const subjectsDiv = document.getElementById('subjects');
    subjectsDiv.innerHTML = ''; // 기존 과목 목록 비우기
    subjectCount = 0; // 과목 카운트 초기화

    const uniqueSubjects = new Set();
    if (Array.isArray(slots)) {
        slots.forEach(slot => {
            // slot[0]은 "수업" 또는 "공강", slot[1]은 과목명
            if (slot && slot.length > 1 && slot[0] === '수업'
                && typeof slot[1] === 'string' && slot[1].trim()) {
                uniqueSubjects.add(slot[1].trim());
            }
        });
    }

    if (uniqueSubjects.size > 0) {
        uniqueSubjects.forEach(subjectName => {
            addSubject(null, subjectName); // 기본값으로 과목 추가
        });
    } else {
        // 불러온 시간표에 수업 과목이 없거나, 아예 빈 시간표인 경우
        // 최소 한 개의 과목 입력 필드를 유지하고 싶다면
        addSubject(null);
        console.log('시간표에 수업 정보가 없거나 빈 시간표입니다. 기본 과목 입력 필드를 추가합니다.');
    }
}
