"""
Simple Streamlit UI for Weather-Based Electricity Load Forecasting
Run with:  streamlit run app.py
"""

import streamlit as st
import joblib
import numpy as np
import os

# Load the trained model
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.pkl")

st.title("⚡ Weather-Based Electricity Load Forecasting")
st.write("Enter weather and time details to predict electricity load.")

# Check if model exists
if not os.path.exists(MODEL_PATH):
    st.error("model.pkl not found! Please run main.py first to train the model.")
    st.stop()

model = joblib.load(MODEL_PATH)

# --- User Inputs ---
st.header("Input Features")

col1, col2 = st.columns(2)

with col1:
    temperature = st.number_input("Temperature (°C)", min_value=-20.0, max_value=50.0, value=25.0, step=0.5)
    humidity = st.number_input("Humidity (%)", min_value=0.0, max_value=100.0, value=60.0, step=1.0)
    wind_speed = st.number_input("Wind Speed (km/h)", min_value=0.0, max_value=50.0, value=10.0, step=0.5)

with col2:
    hour = st.slider("Hour of Day", 0, 23, 12)
    day = st.slider("Day of Month", 1, 31, 15)
    month = st.slider("Month", 1, 12, 6)

# --- Predict ---
if st.button("🔮 Predict Load"):
    features = np.array([[temperature, humidity, wind_speed, hour, day, month]])
    prediction = model.predict(features)[0]
    st.success(f"**Predicted Electricity Load: {prediction:.2f} MW**")

