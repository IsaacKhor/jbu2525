// Web Worker for flight search
class Flight {
    constructor(src, dst, fnum, dtime, atime) {
        this.src = src;
        this.dst = dst;
        this.fnum = fnum;
        this.dtime = new Date(dtime);
        this.atime = new Date(atime);
    }
}

class ValidPlan {
    constructor(flights, airports, totalDur, effectiveDur) {
        this.flights = flights;
        this.airports = airports;
        this.totalDur = totalDur;
        this.totalDays = this.calcDaysTaken();
        this.effectiveDur = effectiveDur;
        this.numOvernights = this.calcOvernights();
    }
    
    calcDaysTaken() {
        const days = new Set();
        for (const flight of this.flights) {
            days.add(flight.dtime.toDateString());
            days.add(flight.atime.toDateString());
        }
        return days.size;
    }
    
    calcOvernights() {
        let count = 0;
        for (let i = 0; i < this.flights.length - 1; i++) {
            if (isOvernight(this.flights[i], this.flights[i + 1])) {
                count++;
            }
        }
        return count;
    }
}

function isOvernight(incoming, outgoing) {
    const layover = outgoing.dtime - incoming.atime;
    const overnightThreshold = 3 * 60 * 60 * 1000;
    
    if (layover > overnightThreshold) {
        const overnightCheckTime = new Date(outgoing.dtime);
        overnightCheckTime.setHours(3, 0, 0, 0);
        return incoming.atime <= overnightCheckTime && overnightCheckTime <= outgoing.dtime;
    }
    return false;
}

function buildCityGraph(flightData) {
    const cityGraph = {};
    for (const flight of flightData) {
        if (!cityGraph[flight.src]) {
            cityGraph[flight.src] = [];
        }
        cityGraph[flight.src].push(flight);
    }
    return cityGraph;
}

function getValidOutgoing(incoming, cityGraph, config) {
    const ret = [];
    const current = incoming.dst;
    
    if (!cityGraph[current]) return ret;
    
    for (const outgoing of cityGraph[current]) {
        const layover = outgoing.dtime - incoming.atime;
        
        if (layover < config.minDayLayover || layover > config.maxDayLayover) {
            continue;
        }
        
        if (isOvernight(incoming, outgoing)) {
            if (layover < config.minNightLayover ||
                layover > config.maxNightLayover ||
                !config.overnightAirports.includes(incoming.dst)) {
                continue;
            }
        }
        
        ret.push(outgoing);
    }
    
    return ret;
}

function buildFlightGraph(flightData, config) {
    const cityGraph = buildCityGraph(flightData);
    const flightGraph = new Map(); // Use Map instead of object
    
    for (const flight of flightData) {
        const outgoing = getValidOutgoing(flight, cityGraph, config);
        flightGraph.set(flight, outgoing.sort((a, b) => b.dtime - a.dtime));
    }
    
    return { cityGraph, flightGraph };
}

function isValidEndpoint(flight, config) {
    if (!config.endAirports.includes(flight.dst)) {
        return false;
    }
    
    const regionalEnd = config.endAirports.slice(1);
    
    if (regionalEnd.includes(flight.dst)) {
        const arrivalTime = flight.atime;
        const cutoffHours = config.homeArrivalCutoff.hours;
        const cutoffMinutes = config.homeArrivalCutoff.minutes;
        
        return arrivalTime.getHours() < cutoffHours ||
               (arrivalTime.getHours() === cutoffHours && arrivalTime.getMinutes() <= cutoffMinutes);
    }
    
    return true;
}

function getNewStartOutgoing(intime, cityGraph, config) {
    const startAirport = config.endAirports[0];
    const ret = [];
    
    if (!cityGraph[startAirport]) return ret;
    
    for (const outgoing of cityGraph[startAirport]) {
        const gap = outgoing.dtime - intime;
        if (gap >= config.minTripGap && gap <= config.maxTripGap) {
            ret.push(outgoing);
        }
    }
    
    return ret;
}

function calcTripDur(flights) {
    if (flights.length === 0) return 0;
    return flights[flights.length - 1].atime - flights[0].dtime;
}

function calcEffectiveDuration(flights, config) {
    let dur = 0;
    for (let i = 0; i < flights.length; i++) {
        const flight = flights[i];
        dur += flight.atime - flight.dtime;
        
        if (i < flights.length - 1) {
            const nextFlight = flights[i + 1];
            const layoverDuration = nextFlight.dtime - flight.atime;
            
            if (!config.endAirports.includes(flight.dst) || layoverDuration <= config.minTripGap) {
                dur += layoverDuration;
            }
        }
    }
    return dur;
}

function isBetterPlan(oldPlan, newPlan, config) {
    const oldTuple = [
        -Math.min(oldPlan.airports.size, config.destCap),
        oldPlan.totalDays,
        oldPlan.flights.length + oldPlan.numOvernights,
        oldPlan.effectiveDur
    ];
    
    const newTuple = [
        -Math.min(newPlan.airports.size, config.destCap),
        newPlan.totalDays,
        newPlan.flights.length + newPlan.numOvernights,
        newPlan.effectiveDur
    ];
    
    for (let i = 0; i < oldTuple.length; i++) {
        if (newTuple[i] < oldTuple[i]) return true;
        if (newTuple[i] > oldTuple[i]) return false;
    }
    
    return false;
}

let isSearching = false;

function performSearch(flightData, config) {
    const { cityGraph, flightGraph } = buildFlightGraph(flightData, config);
    const startAirport = config.endAirports[0];
    const initialFlights = cityGraph[startAirport] || [];
    const validInitialFlights = initialFlights.filter(flight =>
        flight.dtime >= config.startDate
    );
    
    if (validInitialFlights.length === 0) {
        postMessage({ type: 'error', message: 'No valid initial flights found' });
        return;
    }
    
    const queue = validInitialFlights.map(flight => ({
        plan: [flight],
        visited: new Set([flight.dst])
    }));
    
    let iteration = 0;
    const maxIterations = config.maxIterations;
    let bestPlan = null;
    let lastProgressUpdate = 0;
    const progressUpdateInterval = 10000;
    
    isSearching = true;
    
    while (isSearching && queue.length > 0 && iteration < maxIterations) {
        const { plan: curPlan, visited: visitedAirports } = queue.pop();
        const curFlight = curPlan[curPlan.length - 1];
        
        // Check constraints
        if (curFlight.atime - curPlan[0].dtime > config.maxPlanDur ||
            curPlan.length > visitedAirports.size + config.maxDupAirports) {
            iteration++;
            continue;
        }
        
        // Check if valid endpoint
        if (isValidEndpoint(curFlight, config)) {
            if (visitedAirports.size >= config.minDestAirports) {
                const newPlan = new ValidPlan(
                    curPlan.slice(),
                    new Set(visitedAirports),
                    calcTripDur(curPlan),
                    calcEffectiveDuration(curPlan, config)
                );
                
                if (!bestPlan || isBetterPlan(bestPlan, newPlan, config)) {
                    bestPlan = newPlan;
                    postMessage({ 
                        type: 'newBest', 
                        plan: {
                            flights: newPlan.flights,
                            airports: Array.from(newPlan.airports),
                            totalDur: newPlan.totalDur,
                            effectiveDur: newPlan.effectiveDur,
                            totalDays: newPlan.totalDays,
                            numOvernights: newPlan.numOvernights
                        }
                    });
                }
            }
            
            // Start new trip
            if (visitedAirports.size < config.destCap) {
                const newFlights = getNewStartOutgoing(curFlight.atime, cityGraph, config);
                for (const flight of newFlights) {
                    const newVisited = new Set(visitedAirports);
                    newVisited.add(flight.dst);
                    queue.push({
                        plan: curPlan.concat(flight),
                        visited: newVisited
                    });
                }
            }
        }
        
        // Add continuing flights
        const nextFlights = flightGraph.get(curFlight) || [];
        for (const nextFlight of nextFlights) {
            // Pruning rules
            if (curPlan.length < config.minDestAirports / 2 &&
                nextFlight.dst === curPlan[curPlan.length - 1].src) {
                continue;
            }
            
            if (curPlan.length < config.minDestAirports &&
                nextFlight.dst === startAirport) {
                continue;
            }
            
            const newVisited = new Set(visitedAirports);
            newVisited.add(nextFlight.dst);
            queue.push({
                plan: curPlan.concat(nextFlight),
                visited: newVisited
            });
        }
        
        iteration++;
        
        // Send progress updates
        if (iteration - lastProgressUpdate >= progressUpdateInterval) {
            const progress = Math.min((iteration / maxIterations) * 100, 100);
            postMessage({
                type: 'progress',
                progress: progress,
                iteration: iteration,
                maxIterations: maxIterations,
                queueSize: queue.length
            });
            lastProgressUpdate = iteration;
        }
    }
    
    postMessage({ type: 'complete', bestPlan: bestPlan });
}

// Handle messages from main thread
self.onmessage = function(e) {
    const { type, data } = e.data;
    
    switch (type) {
        case 'start':
            // Convert flight data back to Flight objects
            const flightData = data.flightData.map(f => 
                new Flight(f.src, f.dst, f.fnum, f.dtime, f.atime)
            );
            
            // Convert dates in config
            const config = {
                ...data.config,
                startDate: new Date(data.config.startDate),
                endDate: new Date(data.config.endDate)
            };
            
            performSearch(flightData, config);
            break;
            
        case 'stop':
            isSearching = false;
            postMessage({ type: 'stopped' });
            break;
    }
};
