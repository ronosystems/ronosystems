{% extends 'chama_base.html' %}
{% load static %}

{% block title %}Membership Types — Chama Biz{% endblock %}
{% block page_title %}Membership Types{% endblock %}
{% block page_subtitle %}Manage Chama tiers, registration fees, and monthly contributions{% endblock %}

{% block extra_css %}
<style>
    .dash-panel {
        background: #fff;
        border: 2px solid #000;
        border-radius: 4px;
        display: flex;
        flex-direction: column;
    }
    .dash-panel-header {
        background: #f8f9fa;
        border-bottom: 2px solid #000;
        padding: 12px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-weight: 700;
        color: #000;
        border-radius: 4px 4px 0 0;
    }
    
    .table-custom {
        margin-bottom: 0;
    }
    .table-custom th {
        border-bottom: 2px solid #000 !important;
        background: #f8f9fa;
        font-weight: 700;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 12px 20px;
        color: #333;
    }
    .table-custom td {
        padding: 14px 20px;
        vertical-align: middle;
        font-size: 0.9rem;
        border-bottom: 1px solid #dee2e6;
    }
    .table-custom tbody tr:hover {
        background-color: #f8f9fa;
    }

    /* Badges */
    .badge-status {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 50px;
        font-weight: 700;
        font-size: 0.7rem;
        border: 1px solid #000;
        text-transform: uppercase;
    }
    .badge-active { background: #d4edda; color: #155724; }
    .badge-inactive { background: #e2e3e5; color: #383d41; }

    /* Buttons */
    .btn-custom {
        border: 2px solid #000;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.85rem;
        padding: 6px 15px;
        transition: all 0.2s;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .btn-primary-custom {
        background: var(--primary-color);
        color: #fff;
    }
    .btn-primary-custom:hover {
        background: color-mix(in srgb, var(--primary-color) 85%, #000);
        color: #fff;
    }
    .btn-outline-custom {
        background: #fff;
        color: #000;
    }
    .btn-outline-custom:hover {
        background: #f0f2f5;
    }
    .btn-danger-custom {
        background: #dc3545;
        color: #fff;
        border-color: #000;
    }
    .btn-danger-custom:hover {
        background: #c82333;
        color: #fff;
    }

    .action-icon {
        color: #000;
        font-size: 1rem;
        margin: 0 4px;
        transition: color 0.15s;
        display: inline-block;
        text-decoration: none;
    }
    .action-icon:hover { color: var(--primary-color); }
    .action-icon.text-danger:hover { color: #dc3545; }

    /* Info Box */
    .info-box {
        background: var(--soft-tint);
        border-left: 4px solid var(--primary-color);
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 0 4px 4px 0;
    }
    .info-box h6 { color: #000; }
    .info-box p { color: #555; }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid py-2">

    <!-- Info Box -->
    <div class="info-box">
        <h6 class="fw-bold mb-1"><i class="fas fa-info-circle text-primary"></i> What are Membership Types?</h6>
        <p class="mb-0 small">
            Membership types define the joining fees and recurring contributions for different classes of Chama members. 
            When you approve a registration, the member will automatically be assigned their requested type.
        </p>
    </div>

    <!-- Header Actions -->
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
            <h5 class="fw-bold mb-0"><i class="fas fa-id-card text-primary"></i> Membership Tiers</h5>
            <small class="text-muted">{{ types|length }} type{{ types|length|pluralize }} configured</small>
        </div>
        <div>
            <a href="{% url 'chama:membership_type_create' %}" class="btn-custom btn-primary-custom">
                <i class="fas fa-plus"></i> Add New Type
            </a>
        </div>
    </div>

    <!-- Types Table -->
    <div class="dash-panel">
        <div class="table-responsive">
            <table class="table table-hover table-custom">
                <thead>
                    <tr>
                        <th>Type Name</th>
                        <th>Description</th>
                        <th class="text-end">Registration Fee</th>
                        <th class="text-end">Monthly Contribution</th>
                        <th class="text-center">Status</th>
                        <th class="text-end">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in types %}
                    <tr>
                        <td>
                            <div class="fw-bold text-dark">
                                <i class="fas fa-tag me-1" style="color: var(--primary-color); font-size: 0.8rem;"></i>
                                {{ t.name }}
                            </div>
                        </td>
                        <td>
                            <span class="small text-muted">{{ t.description|default:"No description"|truncatewords:15 }}</span>
                        </td>
                        <td class="text-end fw-bold">
                            KES {{ t.registration_fee|floatformat:2 }}
                        </td>
                        <td class="text-end fw-bold">
                            KES {{ t.monthly_contribution|floatformat:2 }}
                        </td>
                        <td class="text-center">
                            {% if t.is_active %}
                                <span class="badge-status badge-active">Active</span>
                            {% else %}
                                <span class="badge-status badge-inactive">Inactive</span>
                            {% endif %}
                        </td>
                        <td class="text-end">
                            <a href="{% url 'chama:membership_type_edit' t.pk %}" class="action-icon" title="Edit">
                                <i class="fas fa-edit"></i>
                            </a>
                            <a href="{% url 'chama:membership_type_delete' t.pk %}" 
                               class="action-icon text-danger" 
                               title="Delete"
                               onclick="return confirm('Delete membership type {{ t.name }}? This cannot be undone.');">
                                <i class="fas fa-trash"></i>
                            </a>
                        </td>
                    </tr>
                    {% empty %}
                    <tr>
                        <td colspan="6" class="text-center py-5">
                            <i class="fas fa-id-card fa-3x text-muted mb-3" style="opacity:0.3;"></i>
                            <h6 class="fw-bold text-muted">No membership types yet</h6>
                            <p class="small text-muted mb-3">
                                You need at least one type before members can register.
                            </p>
                            <a href="{% url 'chama:membership_type_create' %}" class="btn-custom btn-primary-custom btn-sm">
                                <i class="fas fa-plus"></i> Create First Type
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

</div>
{% endblock %}