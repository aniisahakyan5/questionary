import matplotlib.pyplot as plt
import numpy as np
import io
import base64

def calculate_impact_score(incident):
    """
    Calculates a 0-100 score based on 4 pillars.
    Pillar 1: Financial (0-25)
    Pillar 2: Reputational (0-25) - Derived from sentiments
    Pillar 3: Operational (0-25) - Derived from downtime
    Pillar 4: Strategic (0-25) - Derived from severity index
    """
    # Placeholder logic - can be refined with specific metrics
    p1 = min(25, (incident.financial_impact or 0) / 1000000) # 1pt per $M up to 25
    
    # Average trust score (1-10) converted to 0-25 loss
    if incident.sentiments:
        avg_trust = sum(s.trust_score for s in incident.sentiments) / len(incident.sentiments)
        p2 = max(0, 25 - (avg_trust * 2.5))
    else:
        p2 = 0
    
    p3 = min(25, (incident.downtime_days or 0) * 2.5) # 2.5pts per day
    p4 = (incident.strategic_severity or 0) * 5 # 5pts per severity level (0-5)
    
    total = p1 + p2 + p3 + p4
    return min(100, total), [p1, p2, p3, p4]

def generate_radar_chart(scores, pillars=['Financial', 'Reputational', 'Operational', 'Strategic']):
    """
    Generates a base64 encoded radar chart image.
    """
    N = len(pillars)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    
    values = scores + scores[:1]
    
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    
    plt.xticks(angles[:-1], pillars, color='grey', size=12)
    ax.set_rlabel_position(0)
    plt.yticks([5, 10, 15, 20, 25], ["5", "10", "15", "20", "25"], color="grey", size=7)
    plt.ylim(0, 25)
    
    ax.plot(angles, values, linewidth=1, linestyle='solid')
    ax.fill(angles, values, 'b', alpha=0.1)
    
    plt.title("Cyber Impact Dimensions", size=20, color='blue', y=1.1)
    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    
    return img_base64
