# Microgrid Sizing and Optimal Dispatch

Optimisation model of a residential microgrid with PV, battery storage, a diesel generator,
grid connection, an electric vehicle and a heat pump. The model chooses the optimal size of
each asset and how to operate them every 15 minutes over a full year, minimising total
lifetime cost while meeting the household's electricity, EV and thermal comfort needs.

Built in Python with Pyomo and solved with Gurobi.

![Optimal dispatch over 5 winter days](figures/dispatch_5_days.png)

*Optimal dispatch over five winter days: power flows, battery and EV state of charge, and
indoor temperature kept within the comfort band by the heat pump.*

## What the model includes

| Component | Modelling |
|---|---|
| PV | Capacity and inverter size as decision variables; output limited by hourly irradiance profile |
| Battery | Capacity and power rating as decision variables; SOC limits (20–85 %), charge/discharge efficiency |
| Diesel generator | Rated power as decision variable; fuel cost per kWh |
| Grid | Import and export with separate tariffs (can be disabled for off-grid operation) |
| Electric vehicle | Charging only while connected; must reach 80 % SOC at departure |
| Heat pump + building | Lumped-capacitance thermal model of the house; indoor temperature kept within ±2 °C of the setpoint |

**Objective**
- Dispatch: minimise operating cost (fuel + grid import − export revenue).
- Sizing: minimise CAPEX + discounted operating costs over a 20-year horizon (6 % discount rate).

**Building thermal model**

T(t) = T(t−1) + Δt / C · [ COP · (P_heat − P_cool) − P_loss(t) ]

where C is the thermal capacitance of the house and P_loss the heat loss profile.

## Studies

| Script | Question it answers |
|---|---|
| `operational_dispatch.py` | How should fixed-size assets be operated over a few days to minimise cost? |
| `sizing_grid_connected.py` | What is the cost-optimal size of PV, battery, inverters and generator for a grid-connected home? |
| `sizing_off_grid.py` | How do the optimal sizes and cost change when the home is fully off-grid? |
| `sensitivity_capex_budget.py` | How does total cost change when the upfront investment budget is limited? |
| `sensitivity_load_scaling.py` | How do the optimal sizes respond to ±20 % changes in electricity, EV and heating demand? |
| `sensitivity_energy_prices.py` | How do rising import or export prices over the investment horizon change the optimal design? |

Shared files: `param.py` (all technical and economic parameters) and `utils.py`
(data loading, solver call, result checking, printing and plotting).

## Key results

Full year at 15-minute resolution, for a home with 4,000 kWh/yr base load, 15,000 km/yr of EV
driving and heat-pump space heating and cooling.

| | Grid-connected | Off-grid |
|---|---|---|
| PV | 6.5 kWp | 8.0 kWp |
| Battery | 12.1 kWh | 18.3 kWh |
| Diesel generator | none | 14.8 kW (≈ 5,400 kWh/yr) |
| Upfront investment (CAPEX) | € 17,018 | € 24,431 |
| Total annual cost (CAPEX / 20 yr + OPEX) | ≈ € 3,300/yr | ≈ € 4,470/yr |

- With a grid connection, no generator is installed: grid electricity (€ 0.40/kWh) is cheaper
  than generator fuel (€ 0.60/kWh), and the battery stores surplus PV for later use.
- Going off-grid raises the total annual cost by about 35 %. Winter heat-pump demand coincides
  with low PV output, so a large generator and battery are needed to cover those periods.
- In the five-day winter dispatch, the indoor temperature is held mostly at the lower edge of
  the comfort band to save energy, with short pre-heating peaks, and EV charging is scheduled
  within each connection window to reach the departure target at minimum cost.

## How to run

```
pip install -r requirements.txt
python sizing_grid_connected.py
```

Requires a Gurobi installation and licence (free academic licences are available).
The input time series (load, PV, EV presence, heat loss and temperature setpoint at
15-minute resolution) are read from `microgrid_timeseries.csv` (one year, 2021).

## Context

Developed as coursework in the MSc Decentralised Smart Energy Systems (DENSYS).
