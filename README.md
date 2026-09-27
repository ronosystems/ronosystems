# RonoSystems — Multi-Tenant Business Management Platform

[![Django Version](https://img.shields.io/badge/Django-4.2.7-green.svg)](https://www.djangoproject.com/)
[![Python Version](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ronosystems/ronosystems.svg)](https://github.com/ronosystems/ronosystems/stargazers)

A multi-tenant business management platform where many independent companies
run their operations from a single deployment. Each company can subscribe to
one or more business modules — electronics retail, poultry farming, treasury,
and more — with full data isolation between tenants.

## 🚀 Features

### 🏢 Multi-Tenancy
- **Company-based isolation** — Each company has its own data, users, and settings
- **Role-based access control (RBAC)** — Super Admin, Company Admin, Manager, Stock Controller, Cashier, Agent, M-Pesa Agent
- **Branch management** — Multiple store locations per company, with mother/children hierarchy support
- **Secure data separation** — No data leakage between tenants
- **Support Mode** — Super Admins can temporarily view a company's data for troubleshooting

### 🐔 Kuku Biz — Poultry Farming
- **Flocks** — Layers, broilers, mixed; age & mortality tracking
- **Egg production** — Daily collection, cracked/broken/consumed/discarded
- **Bird sales** — Broilers, spent hens, surplus males; auto flock count deduction
- **Feed management** — Types, purchases, consumption, auto inventory sync
- **Health** — Vaccines, treatments, deworming, vet visits
- **Mortality** — Cause, disposal method, financial loss tracking
- **Inventory** — Eggs, feed, vaccines, equipment (per branch, per tray size)
- **Reports** — Monthly performance, best/worst month, branch comparison

### 📦 Inventory Management
- **Product categories** — Electronics, Phones, Accessories
- **IMEI/Serial tracking** — Track individual units with unique identifiers
- **Stock management** — Real-time inventory with low stock alerts
- **Stock movements** — Complete audit trail of all inventory changes

### 💳 Point of Sale (POS)
- **Quick checkout** — Fast and intuitive POS interface
- **Multiple payment methods** — Cash, M-Pesa, Bank Transfer, Card, Points
- **IMEI/Serial scanning** — Quick product lookup
- **Customer management** — Track history and loyalty points
- **Receipt generation** — Professional fiscal receipts

### 👥 Customer Management
- **Customer profiles** — Name, phone, ID number, email
- **Next of kin tracking** — Store emergency contact information
- **Purchase history** — View complete customer purchase history
- **Loyalty points** — Track and redeem points
- **Visit tracking** — Monitor customer visits and engagement

### 💰 Financial Management
- **COGS Tracking** — Cost of Goods Sold per company and branch
- **Profit/Loss tracking** — Monitor business profitability
- **Expense management** — Track operating expenses
- **Purchase records** — Inventory purchases with receipt upload
- **Financial reports** — Daily, weekly, monthly summaries

### 🏦 Treasury
- **Bank accounts** — Multiple accounts per company
- **M-Pesa float** — Track M-Pesa balances
- **Daily records** — Cash reconciliation per branch
- **Branch-scoped balances** — Each branch tracks its own cash

### 📊 Reporting
- **Daily reports** — Sales, revenue, COGS, expenses, profit
- **Weekly reports** — Week-over-week performance
- **Monthly reports** — Month-over-month analysis
- **COGS reports** — Detailed usage and balances
- **Export to CSV** — For external analysis

### 🔐 Security
- **JWT authentication** — Secure API authentication
- **Session-based auth** — Web interface authentication
- **Role-based permissions** — Granular access control
- **CSRF protection** — Cross-site request forgery protection
- **SQL injection prevention** — Django ORM protection

### 🌐 API
- **RESTful API** — Complete API for integration
- **API documentation** — Auto-generated API docs
- **Token authentication** — Secure API access
- **Rate limiting** — Prevent API abuse

## 🏗️ Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Django 4.2.7 |
| **Database** | PostgreSQL (production) / SQLite (development) |
| **Frontend** | HTML5, CSS3, JavaScript, Bootstrap 5 |
| **Charts** | Chart.js |
| **API** | Django REST Framework |
| **Authentication** | JWT, Session-based |
| **Media Storage** | Cloudinary |
| **Deployment** | Gunicorn, Nginx |

### Multi-Tenant Architecture
