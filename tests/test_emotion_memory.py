import emotion_memory as em

def test_average_emotion():
    em.clear()
    em.add_emotion({'Joy': 1.0})
    em.add_emotion({'Anger': 0.5})
    avg = em.average_emotion()
    assert avg['Joy'] > 0
    assert avg['Anger'] > 0

def test_trend():
    em.clear()
    em.add_emotion({'Joy': 0.2})
    em.add_emotion({'Joy': 0.6})
    t = em.trend()
    assert t['Joy'] > 0
