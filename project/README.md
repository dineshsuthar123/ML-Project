# ⚡ Weather-Based Electricity Load Forecasting Using Machine Learning

## Objective

Predict electricity load (demand) using weather conditions and time-of-day features with a simple machine learning model.

## Features Used

| Feature       | Description                  |
|---------------|------------------------------|
| temperature   | Temperature in °C            |
| humidity      | Relative humidity in %       |
| wind_speed    | Wind speed in km/h           |
| hour          | Hour of the day (0–23)       |
| day           | Day of the month (1–31)      |
| month         | Month of the year (1–12)     |

**Target:** `load` — electricity load in MW

## Model Used

- **RandomForestRegressor** (scikit-learn)
- Fallback: LinearRegression (if RandomForest fails)

## Project Structure

```
project/
├── data.csv           # Dataset
├── main.py            # Train model, evaluate, save
├── app.py             # Streamlit UI for predictions
├── model.pkl          # Saved trained model
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## How to Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate dataset (if data.csv does not exist)

```bash
python generate_data.py
```

### 3. Train the model

```bash
python main.py
```

This will:
- Load and preprocess the dataset
- Train a RandomForestRegressor
- Print the RMSE score
- Save the model as `model.pkl`
- Run a sample prediction

### 4. Run the Streamlit app (optional)

```bash
streamlit run app.py
```

Enter weather and time values in the UI to get a predicted electricity load.

## Evaluation Metric

- **RMSE** (Root Mean Squared Error)

