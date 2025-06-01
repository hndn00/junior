# Key Components

**1. StudyPlanNet (Neural Network Model)**

- A 4-layer fully connected neural network (Input → 128 → 64 → 32 → 5 output)
- Utilizes ReLU activation function and Dropout(0.3) to prevent overfitting
- The output classifies study priority into 5 levels (Very High to Very Low) using softmax

**2. StudyPlanDataset (Feature Extraction)**

Generates a 12-dimensional feature vector for each subject:

- Subject importance (normalized weight)
- Major relevance (0 or 1)
- Weekly class hours
- Idle time before/after class
- Day-of-week distribution (Monday to Friday, 5 dimensions)
- Time-of-day distribution (Morning/Afternoon/Evening, 3 dimensions)
- Class continuity index

**3. StudyPlanGenerator (Main Controller)**

- Handles model training and prediction
- Analyzes individual study priority
- Automatically generates weekly study schedules

## Operating Principle

1. **Data Input**: Subject information (name, importance, major relevance) and timetable data
2. **Feature Extraction**: Analyzes each subject’s timetable pattern and converts it into a 12-dimensional vector
3. **Model Training**: Trains the neural network with subject features and labeled priorities
4. **Priority Prediction**: Predicts study priority for each subject using the trained model
5. **Schedule Generation**: Creates a weekly study plan based on predicted priorities and available idle time

## Distinctive Features

- **Timetable-Based Analysis**: Goes beyond basic subject importance and incorporates actual schedule patterns
- **Personalization**: Reflects factors such as major relevance and linkage between class and idle time
- **Practical Output**: Includes pre-study/review separation, recommended study materials, and time allocation

The core idea behind this model is that “a study plan should not be determined solely by subject importance, but also in conjunction with the student's timetable pattern.” For example, a subject followed by a large idle period is more favorable for review and thus may be assigned a higher priority.
