# RonoSystems - Multi-Tenant Business Management Platform

[![Django Version](https://img.shields.io/badge/Django-4.2.7-green.svg)](https://www.djangoproject.com/)
[![Python Version](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ronosystems/ronosystems.svg)](https://github.com/ronosystems/ronosystems/stargazers)

A comprehensive, multi-tenant business management platform designed for electronics and retail businesses. Built with Django, it provides a complete suite of tools for inventory management, point of sale, customer management, financial tracking, and reporting.

## 🚀 Features

### 🏢 Multi-Tenancy
- **Company-based isolation** - Each company has its own data, users, and settings
- **Role-based access control** (RBAC) - Super Admin, Company Admin, Manager, Agent, Cashier
- **Branch management** - Support for multiple store locations per company
- **Secure data separation** - No data leakage between tenants

### 📦 Inventory Management
- **Product categories** - Electronics, Phones, Accessories
- **IMEI/Serial tracking** - Track individual units with unique identifiers
- **Stock management** - Real-time inventory tracking with low stock alerts
- **Stock movements** - Complete audit trail of all inventory changes

### 💳 Point of Sale (POS)
- **Quick checkout** - Fast and intuitive POS interface
- **Multiple payment methods** - Cash, M-Pesa, Bank Transfer, Card, Points
- **IMEI/Serial scanning** - Quick product lookup
- **Customer management** - Track customer history and loyalty points
- **Receipt generation** - Professional fiscal receipts

### 👥 Customer Management
- **Customer profiles** - Name, phone, ID number, email
- **Next of keen tracking** - Store emergency contact information
- **Purchase history** - View complete customer purchase history
- **Loyalty points** - Track and redeem points
- **Visit tracking** - Monitor customer visits and engagement

### 💰 Financial Management
- **COGS Tracking** (Cost of Goods Sold)
- **Profit/Loss tracking** - Monitor business profitability
- **Expense management** - Track operating expenses
- **Purchase records** - Track inventory purchases with receipt upload
- **Financial reports** - Daily, weekly, monthly financial summaries

### 📊 Reporting
- **Daily reports** - Sales, revenue, COGS, expenses, profit
- **Weekly reports** - Week-over-week performance tracking
- **Monthly reports** - Month-over-month business analysis
- **COGS Reports** - Detailed COGS usage and balances
- **Export to CSV** - Export reports for external analysis

### 🔐 Security
- **JWT Authentication** - Secure API authentication
- **Session-based auth** - Web interface authentication
- **Role-based permissions** - Granular access control
- **CSRF protection** - Cross-site request forgery protection
- **SQL injection prevention** - Django's ORM protection

### 🌐 API
- **RESTful API** - Complete API for integration
- **API documentation** - Auto-generated API docs
- **Token authentication** - Secure API access
- **Rate limiting** - Prevent API abuse

## 🏗️ Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Django 4.2.7 |
| **Database** | PostgreSQL / SQLite (Development) |
| **Frontend** | HTML5, CSS3, JavaScript, Bootstrap 5 |
| **Charts** | Chart.js |
| **API** | Django REST Framework |
| **Authentication** | JWT, Session-based |
| **Deployment** | Gunicorn, Nginx |

### Multi-Tenant Architecture
