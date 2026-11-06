import sys
sys.path.insert(0, ".")
from pipeline import transform_rates

def test_valid():
    rates = {"EUR":0.9,"GBP":0.8,"CAD":1.4,"JPY":150,"CHF":0.8,"AUD":1.5}
    clean, rej = transform_rates(rates)
    assert len(clean)==6
    assert len(rej)==0

def test_missing():
    rates = {"EUR":0.9}
    clean, rej = transform_rates(rates)
    assert any(r["currency"]=="GBP" for r in rej)

def test_zero():
    rates = {"EUR":0,"GBP":0.8,"CAD":1.4,"JPY":150,"CHF":0.8,"AUD":1.5}
    clean, rej = transform_rates(rates)
    assert any(r["reason"]=="zero" for r in rej)

def test_negative():
    rates = {"EUR":-1,"GBP":0.8,"CAD":1.4,"JPY":150,"CHF":0.8,"AUD":1.5}
    clean, rej = transform_rates(rates)
    assert any("negative" in r["reason"] for r in rej)

def test_non_numeric():
    rates = {"EUR":"abc","GBP":0.8,"CAD":1.4,"JPY":150,"CHF":0.8,"AUD":1.5}
    clean, rej = transform_rates(rates)
    assert any("non-numeric" in r["reason"] for r in rej)

def test_spike_protection():
    rates = {"EUR":999999,"GBP":0.8,"CAD":1.4,"JPY":150,"CHF":0.8,"AUD":1.5}
    clean, rej = transform_rates(rates)
    assert any("spike" in r["reason"] for r in rej)
