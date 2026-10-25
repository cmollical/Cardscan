"""Durable experiment-wide budget/one-attempt slots; no pricing cache."""
from decimal import Decimal
from uuid import uuid4
from .storage import ResearchStore, BudgetError, micros


class MarketExperimentStore(ResearchStore):
    def __init__(self,path,experiment_id,total_limit='2.00',max_attempts=5):
        if not isinstance(experiment_id,str) or not experiment_id.strip() or len(experiment_id)>120:
            raise ValueError('Explicit experiment ID required')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
            raise ValueError('At most five paid attempts per experiment')
        limit=Decimal(total_limit)
        if not limit.is_finite() or limit <= 0: raise ValueError('Positive finite budget required')
        super().__init__(path)
        self.experiment_id,self.total_limit,self.max_attempts=experiment_id,str(limit),max_attempts
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS market_experiments (
                id TEXT PRIMARY KEY, total_limit INTEGER NOT NULL, max_attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS market_attempts (
                experiment_id TEXT, case_id TEXT, request_id TEXT UNIQUE,
                PRIMARY KEY(experiment_id,case_id));''')
            db.execute('INSERT OR IGNORE INTO market_experiments VALUES (?,?,?)',
                       (experiment_id,micros(limit),max_attempts))
            row=db.execute('SELECT total_limit,max_attempts FROM market_experiments WHERE id=?',(experiment_id,)).fetchone()
            if row!=(micros(limit),max_attempts):
                raise BudgetError('Experiment authorization settings differ from persisted ledger')

    def reserve_case(self,case_id,day,settings):
        if not isinstance(case_id,str) or not case_id.strip(): raise ValueError('Case ID required')
        amount=micros(settings.reservation())
        if amount>micros(settings.per_request_limit_usd):raise BudgetError('Conservative per-request reserve exceeds limit')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used,count=db.execute('SELECT COALESCE(SUM(COALESCE(r.charged,r.reserved)),0),COUNT(*) '
                'FROM market_attempts a JOIN requests r ON r.id=a.request_id WHERE a.experiment_id=?',
                (self.experiment_id,)).fetchone()
            if db.execute('SELECT 1 FROM market_attempts WHERE experiment_id=? AND case_id=?',
                          (self.experiment_id,case_id)).fetchone():raise BudgetError('Case already attempted; paid retry refused')
            if count>=self.max_attempts or used+amount>micros(self.total_limit):
                raise BudgetError('Experiment-wide budget or attempt limit would be exceeded')
            daily,n=db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0),COUNT(*) FROM requests WHERE day=?',(day,)).fetchone()
            if daily+amount>micros(settings.daily_limit_usd) or n>=settings.max_daily_requests:
                raise BudgetError('Existing daily budget or request limit would be exceeded')
            request_id=uuid4().hex
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?)',(request_id,day,amount,None,'reserved','{}'))
            db.execute('INSERT INTO market_attempts VALUES (?,?,?)',(self.experiment_id,case_id,request_id))
        return request_id
