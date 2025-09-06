import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

app = FastAPI()

# --- CORS Middleware ---
# This allows your frontend (running on a different domain) to communicate with this backend.
# In a production environment, you should restrict the origins to your actual frontend's domain.
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1:5500", # Common for Live Server in VS Code
    "null", # To allow opening index.html directly as a file
    "https://lucky-starlight-b2967e.netlify.app" # Add your Netlify URL here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],# origins, # Use the specific origins list for better security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Configuration ---
# It's recommended to store your API key in an environment variable for security.
# For deployment on services like Render, you will set this in the environment variables section.
API_KEY = os.getenv("FMP_API_KEY")
BASE_URL = "https://financialmodelingprep.com/api/v3"


# --- Helper Function for API Calls ---
async def fetch_fmp_data(endpoint: str):
    """A helper function to fetch data from the FinancialModelingPrep API."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key is not configured on the server.")
    
    url = f"{BASE_URL}{endpoint}?apikey={API_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()  # Will raise an exception for 4XX/5XX responses
            data = response.json()
            if not data or (isinstance(data, list) and not data[0]):
                 raise HTTPException(status_code=404, detail="No data found for the given ticker.")
            return data
        except httpx.HTTPStatusError as exc:
            # Try to parse the error message from the API if available
            try:
                error_detail = exc.response.json().get("error", exc.response.text)
            except Exception:
                error_detail = exc.response.text
            raise HTTPException(status_code=exc.response.status_code, detail=f"API request failed: {error_detail}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# --- API Endpoints ---
@app.get("/api/stock/{ticker}")
async def get_stock_all_data(ticker: str):
    """Endpoint to get a combined set of data for a stock ticker."""
    try:
        profile_data = await fetch_fmp_data(f"/profile/{ticker}")
        quote_data = await fetch_fmp_data(f"/quote/{ticker}")
        intraday_data = await fetch_fmp_data(f"/historical-chart/5min/{ticker}")

        if not profile_data or not quote_data:
            raise HTTPException(status_code=404, detail=f"Could not retrieve full data for ticker {ticker}.")

        return {
            "profile": profile_data[0],
            "quote": quote_data[0],
            "chart_intraday": intraday_data
        }
    except HTTPException as e:
        # Re-raise HTTP exceptions from the helper to be handled by FastAPI
        raise e


@app.get("/api/quote/{ticker}")
async def get_quote(ticker: str):
    """Endpoint to get just the latest quote for a stock."""
    quote_data = await fetch_fmp_data(f"/quote/{ticker}")
    return quote_data[0]


@app.get("/api/historical/daily/{ticker}")
async def get_historical_daily(ticker: str):
    """Endpoint to get daily historical data for the past year."""
    # The 'historical-price-full' endpoint provides daily data.
    # We can add parameters for date ranges if needed, but the default is extensive.
    historical_data = await fetch_fmp_data(f"/historical-price-full/{ticker}")
    # The API returns a parent object with a 'historical' key
    return historical_data.get("historical", [])


@app.get("/")
def read_root():
    return {"message": "Stock Analytics API is running."}
