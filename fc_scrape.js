// enable premium (enforced client-side lol)
sessionStorage.setItem('userProfile', '"premium"');

airport_map = new Map(([
    [563, "ABQ,Albuquerque"],
    [577, "ACK,Nantucket"],
    [725, "ALB,Albany"],
    [893, "ATL,Atlanta"],
    [926, "AUS,Austin"],
    [1084, "BDL,Hartford"],
    [1298, "BNA,Nashville"],
    [1335, "BOS,Boston"],
    [1367, "BQN,Aguadilla"],
    [8653, "BUF,Buffalo"],
    [1720, "CHS,Charleston"],
    [1784, "CLE,Cleveland"],
    [2106, "DCA,Washington"],
    [2130, "DEN,Denver"],
    [2138, "DFW,Dallas-Fort Worth"],
    [2296, "DTW,Detroit"],
    [2554, "EWR,New York"],
    [2694, "FLL,Fort Lauderdale"],
    [3394, "HPN,White Plains"],
    [3482, "HYA,Hyannis"],
    [3503, "IAH,Houston"],
    [3684, "ISP,Islip"],
    [3762, "JAX,Jacksonville"],
    [3799, "JFK,New York City"],
    [4425, "LAS,Las Vegas"],
    [4429, "LAX,Los Angeles"],
    [4521, "LGA,New York City"],
    [4888, "MCO,Orlando"],
    [5008, "MHT,Manchester"],
    [5060, "MKE,Milwaukee"],
    [5248, "MSY,New Orleans"],
    [5318, "MVY,Martha's Vineyard"],
    [5662, "ORD,Chicago"],
    [5666, "ORH,Worcester"],
    [5736, "PBI,West Palm Beach"],
    [8651, "PHL,Philadelphia"],
    [5799, "PHX,Phoenix"],
    [5811, "PIT,Pittsburgh"],
    [5926, "PSE,Ponce"],
    [5970, "PVD,Providence"],
    [5984, "PWM,Portland"],
    [6072, "RDU,Raleigh-Durham"],
    [6097, "RIC,Richmond"],
    [6143, "ROC,Rochester"],
    [6170, "RSW,Fort Myers"],
    [6217, "SAV,Savannah"],
    [7848, "SJU,San Juan"],
    [6393, "STT,Saint Thomas"],
    [6396, "STX,Saint Croix"],
    [6450, "SYR,Syracuse"],
    [6622, "TPA,Tampa"],
]));
airport_ids = Array.from(airport_map.keys());

function wait_secs(seconds) {
    return new Promise(resolve => setTimeout(resolve, seconds * 1000));
}

async function get_airport_destinations(src_id) {
    let resp = await fetch(`https://www.flightconnections.com/rt${src_id}.json?v=1097&lang=en&f=ar3035&direction=from&exc=&ids=3035&cl=&flight_direction=from&flight_type=round&airlines=3035&alliance=&classes=&dates=&dates_type=&days_in_destination=&aircrafts=&dep_time_min=&dep_time_max=&arr_time_min=&arr_time_max=&dis_min=&dis_max=&dur_min=&dur_max=`, {
        "credentials": "omit",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=0"
        },
        "referrer": "https://www.flightconnections.com/",
        "method": "GET",
        "mode": "cors"
    });
    let resp_json = await resp.json();
    let dest_ids = resp_json.pts.filter(d => airport_ids.includes(d) && d !== src_id);
    console.log(`Airport ID: ${src_id}, Destinations: ${resp_json.pts.join(', ')}, filtered: ${dest_ids.join(', ')}`);
    return dest_ids;
}

async function get_citypair_schedule(src_id, dest_id) {
    let resp = await fetch("https://www.flightconnections.com/validity.php", {
        "credentials": "omit",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=4"
        },
        "referrer": "https://www.flightconnections.com/",
        "body": `dep=${src_id}&des=${dest_id}&id=3035&startDate=2025&endDate=2026&lang=en`,
        "method": "POST",
        "mode": "cors"
    });
    let resp_json = await resp.json();
    return resp_json.flights;
}

async function get_depart_schedules(src_id) {
    let destinations = await get_airport_destinations(src_id);
    let schedules = {};

    for (const dest_id of destinations) {
        console.log(`Fetching schedule for ${src_id} to ${dest_id} (${airport_map.get(src_id)} to ${airport_map.get(dest_id)})`);
        schedules[dest_id] = await get_citypair_schedule(src_id, dest_id);
        await wait_secs(5);
    }
    return schedules;
}

async function get_all_schedules() {
    let all_schedules = {};
    for (const src_id of airport_ids) {
        console.log(`Fetching schedules for airport ID: ${src_id} (${airport_map.get(src_id)})`);
        all_schedules[src_id] = await get_depart_schedules(src_id);
        // wait for a second between each airport
        await wait_secs(10);
    }
    return all_schedules;
}
