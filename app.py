import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import json
from io import StringIO, BytesIO
import base64
from pymongo import MongoClient

# Page configuration
st.set_page_config(
    page_title="💰 FinTrack - Personal Expense Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern, appealing UI
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
    }
    .metric-card {
        background: rgba(255,255,255,0.1);
        border-radius: 15px;
        padding: 1.5rem;
        border: 1px solid rgba(255,255,255,0.2);
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .sidebar .sidebar-content {
        background: rgba(15,15,35,0.95);
    }
    h1, h2, h3 {
        color: #00ff9d;
    }
    .stButton>button {
        background: linear-gradient(45deg, #00ff9d, #00cc7a);
        color: black;
        border-radius: 10px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB = os.getenv("MONGODB_DB", "fintrack").strip()


def get_database():
    if not MONGODB_URI:
        return None
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client[MONGODB_DB]
    except Exception:
        st.warning("MongoDB connection failed. Data will persist only for this session.")
        return None


db = get_database()


def load_data():
    if db is None:
        return
    try:
        transactions = list(db.transactions.find({}, {"_id": 0}))
        if transactions:
            st.session_state.transactions = pd.DataFrame(transactions)

        budgets_doc = db.budgets.find_one({"_id": "budgets"})
        if budgets_doc and isinstance(budgets_doc.get("data"), dict):
            st.session_state.budgets = budgets_doc["data"]
    except Exception:
        st.warning("Could not load data from MongoDB. Using session storage only.")


def save_data():
    if db is None:
        return
    try:
        db.transactions.delete_many({})
        if not st.session_state.transactions.empty:
            records = st.session_state.transactions.copy()
            records["Date"] = records["Date"].astype(str)
            db.transactions.insert_many(records.to_dict("records"))

        db.budgets.replace_one(
            {"_id": "budgets"},
            {"_id": "budgets", "data": st.session_state.budgets},
            upsert=True,
        )
    except Exception:
        st.warning("Could not save data to MongoDB.")

# Initialize session state
if 'transactions' not in st.session_state:
    st.session_state.transactions = pd.DataFrame(columns=['Date', 'Type', 'Category', 'Amount', 'Description'])

if 'budgets' not in st.session_state:
    st.session_state.budgets = {}

if 'data_loaded' not in st.session_state:
    load_data()
    st.session_state.data_loaded = True

# Categories
EXPENSE_CATEGORIES = ["Food & Dining", "Transport", "Shopping", "Bills & Utilities", "Entertainment", 
                     "Health", "Travel", "Education", "Other"]
INCOME_CATEGORIES = ["Salary", "Freelance", "Investments", "Gifts", "Business", "Other"]

# Sidebar Navigation
st.sidebar.title("💰 FinTrack")
st.sidebar.markdown("### Personal Finance Manager")

page = st.sidebar.radio("Navigate", 
    ["Dashboard", "Add Transaction", "Transactions", "Budgets", "Reports", "Settings"])

# Helper functions
def save_data():
    # For persistence in this demo - in production use database or file
    pass

def calculate_balance(df):
    if df.empty:
        return 0, 0, 0
    income = df[df['Type'] == 'Income']['Amount'].sum()
    expense = df[df['Type'] == 'Expense']['Amount'].sum()
    return income, expense, income - expense

def get_filtered_df(df, start_date=None, end_date=None, category=None, trans_type=None):
    filtered = df.copy()
    if not filtered.empty:
        filtered['Date'] = pd.to_datetime(filtered['Date'])
        if start_date:
            filtered = filtered[filtered['Date'] >= pd.to_datetime(start_date)]
        if end_date:
            filtered = filtered[filtered['Date'] <= pd.to_datetime(end_date)]
        if category and category != "All":
            filtered = filtered[filtered['Category'] == category]
        if trans_type and trans_type != "All":
            filtered = filtered[filtered['Type'] == trans_type]
    return filtered

# Dashboard
if page == "Dashboard":
    st.title("📊 Financial Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_income, total_expense, balance = calculate_balance(st.session_state.transactions)
    
    with col1:
        st.metric("💵 Total Income", f"₹{total_income:,.2f}", delta=None)
    with col2:
        st.metric("💸 Total Expenses", f"₹{total_expense:,.2f}", delta=None)
    with col3:
        st.metric("💰 Balance", f"₹{balance:,.2f}", 
                 delta=f"{balance:.2f}" if balance != 0 else None,
                 delta_color="normal" if balance >= 0 else "inverse")
    with col4:
        if total_income > 0:
            savings_rate = ((total_income - total_expense) / total_income * 100)
            st.metric("📈 Savings Rate", f"{savings_rate:.1f}%")
    
    # Charts
    st.divider()
    col_chart1, col_chart2 = st.columns([2, 1])
    
    with col_chart1:
        st.subheader("Spending Trend")
        if not st.session_state.transactions.empty:
            df = st.session_state.transactions.copy()
            df['Date'] = pd.to_datetime(df['Date'])
            df['Month'] = df['Date'].dt.to_period('M').astype(str)
            
            monthly = df.groupby(['Month', 'Type'])['Amount'].sum().reset_index()
            fig = px.line(monthly, x='Month', y='Amount', color='Type',
                         title="Monthly Income vs Expenses",
                         color_discrete_map={'Income': '#00ff9d', 'Expense': '#ff4d4d'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Add some transactions to see trends")
    
    with col_chart2:
        st.subheader("Expense Breakdown")
        if not st.session_state.transactions.empty:
            expenses = st.session_state.transactions[st.session_state.transactions['Type'] == 'Expense']
            if not expenses.empty:
                fig = px.pie(expenses, values='Amount', names='Category', 
                           title="Expenses by Category",
                           color_discrete_sequence=px.colors.sequential.Plasma)
                st.plotly_chart(fig, use_container_width=True)
    
    # Recent Transactions
    st.subheader("Recent Transactions")
    if not st.session_state.transactions.empty:
        recent = st.session_state.transactions.sort_values('Date', ascending=False).head(5)
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("No transactions yet. Add some from the sidebar!")

# Add Transaction
elif page == "Add Transaction":
    st.title("➕ Add New Transaction")
    
    with st.form("transaction_form"):
        col1, col2 = st.columns(2)
        with col1:
            trans_date = st.date_input("Date", value=date.today())
            trans_type = st.selectbox("Type", ["Expense", "Income"])
        
        with col2:
            if trans_type == "Expense":
                category = st.selectbox("Category", EXPENSE_CATEGORIES)
            else:
                category = st.selectbox("Category", INCOME_CATEGORIES)
            amount = st.number_input("Amount (₹)", min_value=0.01, step=0.01)
        
        description = st.text_input("Description")
        
        submitted = st.form_submit_button("Add Transaction")
        if submitted:
            if amount > 0 and description:
                new_row = {
                    'Date': trans_date.strftime('%Y-%m-%d'),
                    'Type': trans_type,
                    'Category': category,
                    'Amount': amount,
                    'Description': description
                }
                st.session_state.transactions = pd.concat([
                    st.session_state.transactions, 
                    pd.DataFrame([new_row])
                ], ignore_index=True)
                st.success("✅ Transaction added successfully!")
                save_data()
            else:
                st.error("Please fill all fields correctly")

# Transactions
elif page == "Transactions":
    st.title("📋 All Transactions")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("From", value=date.today().replace(day=1))
    with col2:
        end_date = st.date_input("To", value=date.today())
    with col3:
        trans_type_filter = st.selectbox("Type", ["All", "Income", "Expense"])
    
    filtered_df = get_filtered_df(
        st.session_state.transactions, 
        start_date, 
        end_date, 
        None, 
        trans_type_filter if trans_type_filter != "All" else None
    )
    
    if not filtered_df.empty:
        st.dataframe(
            filtered_df.sort_values('Date', ascending=False),
            use_container_width=True,
            hide_index=True
        )
        
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download CSV",
            csv,
            "transactions.csv",
            "text/csv",
            key='download-csv'
        )
    else:
        st.info("No transactions match the filters.")

# Budgets
elif page == "Budgets":
    st.title("🎯 Budget Planner")
    
    st.subheader("Set Monthly Budgets")
    for cat in EXPENSE_CATEGORIES:
        col1, col2 = st.columns([3,1])
        with col1:
            st.write(cat)
        with col2:
            budget = st.number_input(f"Budget for {cat}", 
                                   min_value=0.0, 
                                   value=float(st.session_state.budgets.get(cat, 0)),
                                   key=f"budget_{cat}")
            st.session_state.budgets[cat] = budget
    
    if st.button("Save Budgets"):
        st.success("Budgets updated!")
    
    # Budget vs Actual
    st.divider()
    st.subheader("Budget vs Actual (This Month)")
    
    current_month = datetime.now().strftime('%Y-%m')
    monthly_exp = st.session_state.transactions.copy()
    if not monthly_exp.empty:
        monthly_exp['Date'] = pd.to_datetime(monthly_exp['Date'])
        monthly_exp = monthly_exp[monthly_exp['Date'].dt.strftime('%Y-%m') == current_month]
        monthly_exp = monthly_exp[monthly_exp['Type'] == 'Expense']
        
        if not monthly_exp.empty:
            spent = monthly_exp.groupby('Category')['Amount'].sum()
            
            budget_data = []
            for cat in EXPENSE_CATEGORIES:
                b = st.session_state.budgets.get(cat, 0)
                s = spent.get(cat, 0)
                budget_data.append({
                    'Category': cat,
                    'Budget': b,
                    'Spent': s,
                    'Remaining': b - s
                })
            
            budget_df = pd.DataFrame(budget_data)
            st.dataframe(budget_df, use_container_width=True)
            
            # Progress bars
            for _, row in budget_df.iterrows():
                if row['Budget'] > 0:
                    progress = min(row['Spent'] / row['Budget'], 1.0)
                    st.progress(progress, text=f"{row['Category']}: ₹{row['Spent']:.0f} / ₹{row['Budget']:.0f}")

# Reports & Analytics
elif page == "Reports":
    st.title("📈 Detailed Reports")
    
    tab1, tab2, tab3 = st.tabs(["Category Analysis", "Time Trends", "Summary"])
    
    with tab1:
        if not st.session_state.transactions.empty:
            expenses = st.session_state.transactions[st.session_state.transactions['Type'] == 'Expense']
            if not expenses.empty:
                cat_spend = expenses.groupby('Category')['Amount'].sum().reset_index()
                fig = px.bar(cat_spend, x='Category', y='Amount', 
                           title="Spending by Category",
                           color='Amount',
                           color_continuous_scale='Viridis')
                st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        if not st.session_state.transactions.empty:
            df = st.session_state.transactions.copy()
            df['Date'] = pd.to_datetime(df['Date'])
            df['Month'] = df['Date'].dt.strftime('%Y-%m')
            
            monthly_summary = df.groupby(['Month', 'Type'])['Amount'].sum().unstack(fill_value=0)
            fig = go.Figure()
            if 'Income' in monthly_summary.columns:
                fig.add_trace(go.Bar(x=monthly_summary.index, y=monthly_summary['Income'], name='Income', marker_color='#00ff9d'))
            if 'Expense' in monthly_summary.columns:
                fig.add_trace(go.Bar(x=monthly_summary.index, y=monthly_summary['Expense'], name='Expense', marker_color='#ff4d4d'))
            fig.update_layout(title="Monthly Income & Expenses", barmode='group')
            st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Key Insights")
        income, expense, bal = calculate_balance(st.session_state.transactions)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Net Worth", f"₹{bal:,.2f}")
        with col2:
            if expense > 0:
                st.metric("Biggest Expense Category", 
                         st.session_state.transactions[st.session_state.transactions['Type']=='Expense'].groupby('Category')['Amount'].sum().idxmax())
        
        st.info("💡 Pro tip: Review your spending patterns monthly and adjust budgets accordingly.")

# Settings
elif page == "Settings":
    st.title("⚙️ Settings")
    
    st.subheader("Data Management")
    if st.button("Clear All Data"):
        if st.checkbox("I understand this is irreversible"):
            st.session_state.transactions = pd.DataFrame(columns=['Date', 'Type', 'Category', 'Amount', 'Description'])
            st.session_state.budgets = {}
            if db is not None:
                db.transactions.delete_many({})
                db.budgets.delete_many({})
            st.success("All data cleared!")
    
    st.subheader("Theme & Preferences")
    st.info("Dark theme is enabled by default for better visibility.")
    
    st.subheader("Export / Import")
    if not st.session_state.transactions.empty:
        csv = st.session_state.transactions.to_csv(index=False).encode()
        st.download_button("Export All Data", csv, "fintrack_backup.csv", "text/csv")

st.sidebar.markdown("---")
st.sidebar.caption("Built with ❤️ using Streamlit\n(For demo - data persists only in session)")