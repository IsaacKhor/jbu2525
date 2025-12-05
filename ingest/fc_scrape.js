// enable premium (enforced client-side lol)
sessionStorage.setItem('userProfile', '"premium"');

airports_csv = `
ALB,Albany,725
ATL,Atlanta,893
AUS,Austin,926
BDL,Hartford,1084
BNA,Nashville,1298
BOS,Boston,1335
BQN,Aguadilla,1367
BUF,Buffalo,8653
CHS,Charleston,1720
CLE,Cleveland,1784
CUN,Cancun,1987
DCA,Washington,2106
DEN,Denver,2130
DFW,Dallas-Fort Worth,2138
DTW,Detroit,2296
EWR,New York,2554
FLL,Fort Lauderdale,2694
HPN,White Plains,3394
HYA,Hyannis,3482
IAH,Houston,3503
ISP,Islip,3684
JAX,Jacksonville,3762
JFK,New York City,3799
KIN,Kingston,4117
LAS,Las Vegas,4425
LAX,Los Angeles,4429
LGA,New York City,4521
MBJ,Montego Bay,4859
MCO,Orlando,4888
MHT,Manchester,5008
MKE,Milwaukee,5060
MSY,New Orleans,5248
MVY,Martha's Vineyard,5318
NAS,Nassau,5419
ORD,Chicago,5662
ORH,Worcester,5666
PBI,West Palm Beach,5736
PHL,Philadelphia,8651
PHX,Phoenix,5799
PIT,Pittsburgh,5811
PJU,Punta Cana,5960
POP,Puerto Plata,5883
PSE,Ponce,5926
PVD,Providence,5970
PWM,Portland,5984
RDU,Raleigh-Durham,6072
RIC,Richmond,6097
ROC,Rochester,6143
RSW,Fort Myers,6170
SAV,Savannah,6217
SDQ,Santo Domingo,6260
SJU,San Juan,7848
STI,Santiago de los Caballeros,6384
STT,Saint Thomas,6393
STX,Saint Croix,6396
SYR,Syracuse,6450
TPA,Tampa,6622
`

airport_map = new Map(airports_csv.trim().split('\n').map(line => {
    let parts = line.split(',');
    return [parseInt(parts[2]), parts[0] + ',' + parts[1]];
}));
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

scheds = await get_all_schedules();
