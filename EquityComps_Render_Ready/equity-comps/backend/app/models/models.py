from sqlalchemy import (
    Column, String, Float, BigInteger, Integer, DateTime, Boolean,
    Text, ForeignKey, Index, UniqueConstraint, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class Company(Base):
    __tablename__ = "companies"

    ticker = Column(String(10), primary_key=True)
    name = Column(String(255), nullable=False)
    sector = Column(String(100))
    industry = Column(String(150))
    cik = Column(String(20))
    in_sp500 = Column(Boolean, default=False)
    in_nasdaq100 = Column(Boolean, default=False)
    exchange = Column(String(20))
    currency = Column(String(5), default="USD")
    is_active = Column(Boolean, default=True)
    # Cached metadata — avoids re-fetching every refresh
    meta_cached_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    market_prices = relationship("MarketPrice", back_populates="company", uselist=False)
    financial_statements = relationship("FinancialStatement", back_populates="company", uselist=False)
    calculated_multiples = relationship("CalculatedMultiple", back_populates="company", uselist=False)

    __table_args__ = (
        Index("ix_companies_sector", "sector"),
        Index("ix_companies_industry", "industry"),
    )


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), unique=True, nullable=False)
    price = Column(Numeric(20, 4))
    prev_close = Column(Numeric(20, 4))
    day_change_pct = Column(Numeric(10, 4))
    market_cap = Column(BigInteger)
    volume = Column(BigInteger)
    avg_volume_30d = Column(BigInteger)
    week_52_high = Column(Numeric(20, 4))
    week_52_low = Column(Numeric(20, 4))
    shares_outstanding = Column(BigInteger)
    dividend_yield = Column(Numeric(10, 6))   # NEW: annual dividend yield %
    refreshed_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="market_prices")

    __table_args__ = (Index("ix_market_prices_ticker", "ticker"),)


class FinancialStatement(Base):
    __tablename__ = "financial_statements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), unique=True, nullable=False)
    fiscal_year_end = Column(String(20))
    period_type = Column(String(10), default="LTM")

    # Filing metadata (NEW)
    filing_form = Column(String(20))          # 10-K, 10-Q
    fiscal_year = Column(Integer)
    fiscal_quarter = Column(String(5))        # Q1..Q4 / FY
    period_end_date = Column(String(20))      # YYYY-MM-DD

    # Income Statement — raw from EDGAR
    revenue = Column(BigInteger)
    revenue_prior = Column(BigInteger)        # NEW: prior-year revenue for growth calc
    gross_profit = Column(BigInteger)
    ebitda = Column(BigInteger)
    ebit = Column(BigInteger)
    net_income = Column(BigInteger)
    eps_diluted = Column(Numeric(20, 4))
    free_cash_flow = Column(BigInteger)       # NEW: CFO - CapEx

    # Balance Sheet — raw from EDGAR
    total_assets = Column(BigInteger)
    total_debt = Column(BigInteger)
    cash_and_equivalents = Column(BigInteger)
    shareholders_equity = Column(BigInteger)
    shares_outstanding_bs = Column(BigInteger)

    # Derived raw fields
    net_debt = Column(BigInteger)
    book_value_per_share = Column(Numeric(20, 4))

    # Operating cash flow (stored separately — FCF = CFO - CapEx)
    operating_cash_flow = Column(BigInteger)

    # Annualized income statement fields (interim period × factor).
    # Only populated for Q1 / H1 / 9M filings — never for annual periods.
    # Balance sheet items are NEVER annualized.
    annualized_revenue             = Column(BigInteger)
    annualized_gross_profit        = Column(BigInteger)
    annualized_ebitda              = Column(BigInteger)
    annualized_ebit                = Column(BigInteger)
    annualized_net_income          = Column(BigInteger)
    annualized_eps_diluted         = Column(Numeric(20, 4))
    annualized_operating_cash_flow = Column(BigInteger)
    annualized_free_cash_flow      = Column(BigInteger)

    # TTM income statement fields (sum of last 4 quarters). Priority 1.
    ttm_revenue             = Column(BigInteger)
    ttm_gross_profit        = Column(BigInteger)
    ttm_ebitda              = Column(BigInteger)
    ttm_ebit                = Column(BigInteger)
    ttm_net_income          = Column(BigInteger)
    ttm_eps_diluted         = Column(Numeric(20, 4))
    ttm_operating_cash_flow = Column(BigInteger)
    ttm_free_cash_flow      = Column(BigInteger)

    # Financial basis transparency
    financial_basis       = Column(String(30))   # "TTM" / "Annualized Q1" / "Annual FY2024" etc.
    interim_period_months = Column(Integer)       # 3, 6, or 9

    data_source = Column(String(50), default="SEC_EDGAR")
    filing_date = Column(DateTime(timezone=True))
    refreshed_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="financial_statements")

    __table_args__ = (Index("ix_financial_statements_ticker", "ticker"),)


class CalculatedMultiple(Base):
    __tablename__ = "calculated_multiples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), unique=True, nullable=False)

    enterprise_value = Column(BigInteger)

    # Core multiples
    pe_ratio = Column(Numeric(20, 4))
    ev_ebitda = Column(Numeric(20, 4))
    ev_sales = Column(Numeric(20, 4))
    price_to_book = Column(Numeric(20, 4))
    roe = Column(Numeric(20, 4))
    ebitda_margin = Column(Numeric(20, 4))
    net_debt_ebitda = Column(Numeric(20, 4))

    # NEW metrics
    fcf_yield = Column(Numeric(20, 4))        # FCF / Market Cap %
    revenue_growth = Column(Numeric(20, 4))   # (Rev - Rev_prior) / Rev_prior %
    gross_margin = Column(Numeric(20, 4))     # Gross Profit / Revenue %
    dividend_yield = Column(Numeric(10, 6))   # Sourced from market data
    eps_growth = Column(Numeric(20, 4))       # Placeholder — populated if available

    # Institutional research metrics (NEW)
    eps = Column(Numeric(20, 4))                  # Net Income / Shares Outstanding
    debt_to_equity = Column(Numeric(20, 4))       # Total Debt / Shareholders' Equity

    # Financial basis transparency — which period underlies each multiple
    financial_basis  = Column(String(30))   # "TTM" / "Annualized Q1" / "Annual FY2024"
    pe_basis         = Column(String(30))   # basis for P/E specifically
    ev_ebitda_basis  = Column(String(30))   # basis for EV/EBITDA specifically
    ev_sales_basis   = Column(String(30))   # basis for EV/Sales specifically
    fcf_yield_basis  = Column(String(30))   # basis for FCF Yield specifically

    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="calculated_multiples")

    __table_args__ = (Index("ix_calculated_multiples_ticker", "ticker"),)
